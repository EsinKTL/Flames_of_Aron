"""LLM writer, deterministic answer validator, retry and fallback (Progress Report, Section 6).

    answer_question(query, engine, ...)   end-to-end: build_evidence_bundle -> write_answer -> Answer
    write_answer(bundle, ...)             EvidenceBundle -> LLM (with 1 retry) or fallback_answer -> Answer
    validate_response(text, bundle)       deterministic post-generation check (citations, R-007 conflicts, R-006 gaps)
    make_llm_classifier(...)              optional ambiguity hook for router.route(query, llm_classify=...)

Rules enforced here:
  * The LLM sees ONLY the EvidenceBundle dictionary.
  * answer_type ('answer', 'no_data', 'out_of_scope') is copied from bundle['answer_type'] and never changed.
  * Every S-XXX, F-XXX, C-XXX and PSI-XX citation in the generated text must exist in the bundle.
  * Every conflict in bundle['conflicts'] must have both values represented in the answer (R-007).
  * Refusal bundles ('no_data', 'out_of_scope') must explicitly state unavailability / out-of-scope (R-006).
  * On validation failure, the writer retries at most once with the validation errors; if the second attempt
    fails (or the API errors / no key is configured), it falls back to evidence.fallback_answer(bundle).
"""
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

import contracts
import evidence
import router

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR / ".env"

DEFAULT_MODELS = {
    "mistral": "mistral-small-latest",
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
}
GEMINI_FALLBACK_MODELS = (
    "gemini-3.6-flash",
    "gemini-3.5-flash",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemini-3-flash-preview",
    "gemma-4-26b-a4b-it",
)
_RETIRED_GEMINI_MODELS = set()

_LAST_MISTRAL_TS = 0.0
MISTRAL_MIN_INTERVAL_S = 1.05
_LAST_GEMINI_TS = 0.0
GEMINI_MIN_INTERVAL_S = 1.0


def load_dotenv(dotenv_path=None):
    """Read simple KEY=VALUE lines from .env without third-party dependencies."""
    env = {}
    path = Path(dotenv_path if dotenv_path is not None else ENV_PATH)
    if not path.is_file():
        return env
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        v = v.strip().strip("'").strip('"')
        if k:
            env[k] = v
            os.environ.setdefault(k, v)
    return env


def resolve_provider_and_key(provider=None, model=None):
    """Determine (provider, model, api_key) from arguments, environment variables, or .env."""
    load_dotenv()
    if provider is not None:
        p = provider.strip().lower()
        if p in ("none", "stub", "fallback", ""):
            return "none", "evidence-summary", None
        if p == "mistral":
            key = os.environ.get("MISTRAL_API_KEY")
            return ("mistral", model or DEFAULT_MODELS["mistral"], key) if key else ("none", "evidence-summary", None)
        if p == "gemini":
            key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
            return ("gemini", model or DEFAULT_MODELS["gemini"], key) if key else ("none", "evidence-summary", None)
        if p == "groq":
            key = os.environ.get("GROQ_API_KEY")
            return ("groq", model or DEFAULT_MODELS["groq"], key) if key else ("none", "evidence-summary", None)
        raise ValueError(f"Unknown LLM provider: {provider!r}. Expected 'mistral', 'gemini', 'groq', or 'none'.")

    # Auto-detect from environment
    if os.environ.get("MISTRAL_API_KEY"):
        return "mistral", model or DEFAULT_MODELS["mistral"], os.environ["MISTRAL_API_KEY"]
    if os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"):
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        return "gemini", model or DEFAULT_MODELS["gemini"], key
    if os.environ.get("GROQ_API_KEY"):
        return "groq", model or DEFAULT_MODELS["groq"], os.environ["GROQ_API_KEY"]
    return "none", "evidence-summary", None


# --- HTTP LLM Clients ---------------------------------------------------------

def _http_post_json(url, payload, headers, timeout=45, max_retries=3, min_backoff=1.5):
    data = json.dumps(payload).encode("utf-8")
    last_err = None
    for attempt in range(max_retries):
        req = urllib.request.Request(url, data=data, headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            last_err = RuntimeError(f"HTTP {e.code}: {body[:300]}")
            if e.code in (429, 500, 502, 503, 504) and attempt < max_retries - 1:
                time.sleep(min_backoff * (2 ** attempt))
                continue
            raise last_err from e
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                time.sleep(min_backoff * (2 ** attempt))
                continue
            raise last_err from e
    raise last_err


def _call_mistral(messages, model, api_key, temperature=0.1, timeout=45):
    global _LAST_MISTRAL_TS
    elapsed = time.time() - _LAST_MISTRAL_TS
    if elapsed < MISTRAL_MIN_INTERVAL_S:
        time.sleep(MISTRAL_MIN_INTERVAL_S - elapsed)
    url = "https://api.mistral.ai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    res = _http_post_json(url, payload, headers, timeout=timeout, max_retries=3, min_backoff=2.0)
    _LAST_MISTRAL_TS = time.time()
    return res["choices"][0]["message"]["content"].strip(), model


def _call_groq(messages, model, api_key, temperature=0.1, timeout=45):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "FlamesOfAron/1.0",
    }
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
    }
    res = _http_post_json(url, payload, headers, timeout=timeout, max_retries=3, min_backoff=1.5)
    return res["choices"][0]["message"]["content"].strip(), model


def _call_gemini(messages, model, api_key, temperature=0.1, timeout=45):
    global _LAST_GEMINI_TS
    system_parts = [m["content"] for m in messages if m["role"] == "system"]
    user_parts = [m["content"] for m in messages if m["role"] != "system"]

    headers = {
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }
    candidates = [m for m in [model] + [x for x in GEMINI_FALLBACK_MODELS if x != model] if m not in _RETIRED_GEMINI_MODELS]
    if not candidates:
        candidates = [model] + [x for x in GEMINI_FALLBACK_MODELS if x != model]
    last_err = None
    for cand_model in candidates:
        elapsed = time.time() - _LAST_GEMINI_TS
        if elapsed < GEMINI_MIN_INTERVAL_S:
            time.sleep(GEMINI_MIN_INTERVAL_S - elapsed)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{cand_model}:generateContent"
        is_gemma = cand_model.startswith("gemma")
        if is_gemma:
            combined_text = ("\n\n".join(system_parts) + "\n\n" if system_parts else "") + "\n\n".join(user_parts)
            req_payload = {
                "contents": [{"role": "user", "parts": [{"text": combined_text}]}],
                "generationConfig": {"temperature": temperature},
            }
        else:
            gen_cfg = {"temperature": temperature}
            if "lite" not in cand_model:
                gen_cfg["thinkingConfig"] = {"thinkingBudget": 0}
            req_payload = {
                "contents": [{"role": "user", "parts": [{"text": "\n\n".join(user_parts)}]}],
                "generationConfig": gen_cfg,
            }
            if system_parts:
                req_payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
        try:
            res = _http_post_json(url, req_payload, headers, timeout=timeout, max_retries=1, min_backoff=1.5)
            _LAST_GEMINI_TS = time.time()
            parts = res["candidates"][0]["content"]["parts"]
            text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
            if not text:
                text = "".join(p.get("text", "") for p in parts).strip()
            text = re.sub(r"<thought>.*?</thought>", "", text, flags=re.S).strip()
            return text, cand_model
        except Exception as e:
            last_err = e
            err_str = str(e)
            if "HTTP 404" in err_str or "no longer available" in err_str or "HTTP 429" in err_str:
                _RETIRED_GEMINI_MODELS.add(cand_model)
                continue
            if "timed out" in err_str.lower() or "HTTP 400" in err_str:
                continue
            raise
    raise last_err


def call_llm(messages, provider=None, model=None, api_key=None, temperature=0.1, timeout=45):
    """Call the configured LLM provider and return (text, 'provider/model')."""
    if api_key is None or provider is None or model is None:
        prov, mod, key = resolve_provider_and_key(provider, model)
    else:
        prov, mod, key = provider, model, api_key
    if prov == "none" or not key:
        raise RuntimeError("No LLM provider or API key configured.")
    if prov == "mistral":
        text, used_model = _call_mistral(messages, mod, key, temperature=temperature, timeout=timeout)
    elif prov == "gemini":
        text, used_model = _call_gemini(messages, mod, key, temperature=temperature, timeout=timeout)
    elif prov == "groq":
        text, used_model = _call_groq(messages, mod, key, temperature=temperature, timeout=timeout)
    else:
        raise ValueError(f"Unsupported provider: {prov}")
    return text, f"{prov}/{used_model}"


# --- Router Optional Classifier Hook ------------------------------------------

def llm_classify(query, candidate_intents, provider=None, model=None, llm_fn=None):
    """Classify an ambiguous question among candidate_intents for router.route()."""
    candidates = list(candidate_intents)
    if not candidates:
        return "general"
    prompt = (
        "Classify the user question into exactly ONE of the following intents:\n"
        f"Candidates: {', '.join(candidates)}\n\n"
        f"Question: {query}\n\n"
        "Reply with ONLY the single intent name from the candidates list and nothing else."
    )
    messages = [{"role": "user", "content": prompt}]
    try:
        if llm_fn is not None:
            raw = llm_fn(messages)
            text = raw[0] if isinstance(raw, tuple) else str(raw)
        else:
            prov, mod, key = resolve_provider_and_key(provider, model)
            if prov == "none" or not key:
                return candidates[0]
            text, _ = call_llm(messages, provider=prov, model=mod, api_key=key, temperature=0.0, timeout=15)
        token = re.sub(r"[^a-z_]", "", text.strip().lower().split()[0]) if text.strip() else ""
        return token if token in candidates else "general"
    except Exception:
        return candidates[0]


def make_llm_classifier(provider=None, model=None, llm_fn=None):
    """Return a callable (query, candidate_intents) -> intent suitable for router.route()."""
    return lambda query, candidates: llm_classify(query, candidates, provider=provider, model=model, llm_fn=llm_fn)


# --- Allowed Citations & Extraction -------------------------------------------

def allowed_bundle_ids(bundle):
    """Return sets of valid citation identifiers present in the bundle."""
    f_ids = {f["id"] for f in bundle.get("facts", [])}
    for g in bundle.get("gaps", []):
        f_ids.update(re.findall(r"F-\d{3}", g))

    c_ids = set()
    for calc in bundle.get("calculations", []):
        cc = calc.get("cross_check")
        if isinstance(cc, dict) and cc.get("id"):
            c_ids.add(cc["id"])
        for fid in re.findall(r"F-\d{3}", str(calc.get("label", ""))):
            f_ids.add(fid)

    s_ids = set()
    s_pages = {}
    psi_ids = set()
    psi_tests = {}

    for ch in bundle.get("chunks", []):
        sid = ch["source_id"]
        s_ids.add(sid)
        s_pages.setdefault(sid, set()).add(str(ch["page"]))
        for pid in re.findall(r"PSI-\d+", ch.get("text", "")):
            psi_ids.add(pid)
    for t in bundle.get("tests", []):
        if t.get("source_id"):
            s_ids.add(t["source_id"])
    for row in bundle.get("table_rows", []):
        for refs in row.get("evidence", {}).values():
            for r in refs:
                sid = r["source_id"]
                s_ids.add(sid)
                s_pages.setdefault(sid, set()).add(str(r["page"]))
    for conf in bundle.get("conflicts", []):
        for side in (conf.get("source_1", ""), conf.get("source_2", "")):
            for sid in re.findall(r"S-\d{3}", side):
                s_ids.add(sid)
            for pid in re.findall(r"PSI-\d+", side):
                psi_ids.add(pid)
            for m in re.finditer(r"(S-\d{3})[^\];]*?\bp\.?\s*(\d+)", side):
                s_pages.setdefault(m.group(1), set()).add(m.group(2))
    for src in bundle.get("sources", []):
        if src.get("found"):
            sid = src["id"]
            if sid.startswith("S-"):
                s_ids.add(sid)
            elif sid.startswith("F-"):
                f_ids.add(sid)

    for t in bundle.get("tests", []):
        pid = t["psi_id"]
        psi_ids.add(pid)
        psi_tests.setdefault(pid, set()).add(str(t["test"]))
    for src in bundle.get("sources", []):
        if src.get("found") and src["id"].startswith("PSI-"):
            psi_ids.add(src["id"])

    return {
        "F": f_ids,
        "C": c_ids,
        "S": s_ids,
        "S_pages": s_pages,
        "PSI": psi_ids,
        "PSI_tests": psi_tests,
    }


_S_CITE_RE = re.compile(r"\b(S-\d{3})(?:(?:\s*[,:]?\s*(?:p\.?|page|pp\.?)\s*|\s*:\s*)(\d+))?\b")
_F_CITE_RE = re.compile(r"\b(F-\d{3})\b")
_C_CITE_RE = re.compile(r"\b(C-\d{3})\b")
_PSI_CITE_RE = re.compile(r"\b(PSI-\d+)(?:(?:\s*[,:]?\s*test\s*#?\s*|\s*:\s*test)([A-Za-z0-9_-]+))?\b", re.I)


def extract_citations(text, bundle):
    """Extract and normalize citations from generated text; return (valid_citations, hallucinated_citations)."""
    allowed = allowed_bundle_ids(bundle)
    valid = []
    hallucinated = []

    for m in _F_CITE_RE.finditer(text):
        fid = m.group(1)
        if fid in allowed["F"]:
            valid.append(fid)
        else:
            hallucinated.append(fid)

    for m in _C_CITE_RE.finditer(text):
        cid = m.group(1)
        if cid in allowed["C"]:
            valid.append(cid)
        else:
            hallucinated.append(cid)

    for m in _PSI_CITE_RE.finditer(text):
        pid = m.group(1).upper()
        t_id = m.group(2)
        if pid not in allowed["PSI"]:
            hallucinated.append(f"{pid}:test{t_id}" if t_id else pid)
            continue
        if t_id is not None:
            known_tests = allowed["PSI_tests"].get(pid, set())
            if known_tests and t_id not in known_tests:
                hallucinated.append(f"{pid}:test{t_id}")
            else:
                valid.append(f"{pid}:test{t_id}")
        else:
            valid.append(pid)

    for m in _S_CITE_RE.finditer(text):
        sid = m.group(1)
        page = m.group(2)
        if sid not in allowed["S"]:
            hallucinated.append(f"{sid}:{page}" if page else sid)
            continue
        if page is not None:
            valid.append(f"{sid}:{page}")
        else:
            pages = allowed["S_pages"].get(sid, set())
            if len(pages) == 1:
                valid.append(f"{sid}:{next(iter(pages))}")
            else:
                valid.append(sid)

    return list(dict.fromkeys(valid)), list(dict.fromkeys(hallucinated))


# --- Deterministic Validator --------------------------------------------------

def _conflict_numbers(val_str):
    """Extract primary numerical tokens from a conflict value string."""
    stripped = re.sub(r"\([^)]*\)", " ", str(val_str))
    nums = re.findall(r"\d+(?:\.\d+)?", stripped)
    if not nums:
        nums = re.findall(r"\d+(?:\.\d+)?", str(val_str))
    return nums


def _side_present_in_text(val_str, text, text_floats):
    val_clean = str(val_str).strip().lower()
    if val_clean and val_clean in text.lower():
        return True
    nums = _conflict_numbers(val_str)
    if not nums:
        tokens = [w.lower() for w in re.findall(r"[A-Za-z0-9_.-]+", str(val_str)) if len(w) >= 2]
        return any(t in text.lower() for t in tokens) if tokens else True
    for n in nums:
        if n in text:
            return True
        try:
            fn = float(n)
            if any(abs(fn - tf) < 1e-6 for tf in text_floats):
                return True
        except ValueError:
            pass
    return False


_OUT_OF_SCOPE_RE = re.compile(
    r"out of scope|outside (?:the )?scope|not covered|not part of|beyond (?:the )?scope|does not cover",
    re.I,
)
_NO_DATA_RE = re.compile(
    r"not available|no data|no [a-z0-9 -]{1,30} data|does not contain|no source|no results|unknown|"
    r"not in (?:the |our )?(?:repo|repository|corpus|data)|cannot be retrieved|unavailable|data gap",
    re.I,
)


def validate_response(text, bundle):
    """Validate an LLM-generated answer text against the EvidenceBundle.

    Returns a dict:
      {
        "passed": bool,
        "errors": list[str],
        "citations": list[str],
        "hallucinated_citations": list[str],
      }
    """
    errors = []
    if not text or not str(text).strip():
        return {
            "passed": False,
            "errors": ["Empty response from LLM."],
            "citations": [],
            "hallucinated_citations": [],
        }

    valid_cites, hallucinated_cites = extract_citations(text, bundle)
    if hallucinated_cites:
        errors.append(f"Hallucinated citation(s) not in bundle: {', '.join(hallucinated_cites)}.")

    allowed = allowed_bundle_ids(bundle)
    has_any_citable = bool(allowed["F"] or allowed["C"] or allowed["S"] or allowed["PSI"])
    is_medical_oos = (
        bundle.get("answer_type") == "out_of_scope"
        and (bundle.get("route") or {}).get("out_of_scope_reason") == "medical"
    )
    if has_any_citable and not is_medical_oos and not valid_cites:
        errors.append("Answer must include at least one valid citation ID from the bundle (e.g. [S-XXX p.Y], [F-XXX], [PSI-XX:testY]).")

    # Rule R-007: Conflict check
    if bundle.get("conflicts") and bundle.get("answer_type") == "answer":
        text_nums = re.findall(r"\d+(?:\.\d+)?", text)
        text_floats = []
        for x in text_nums:
            try:
                text_floats.append(float(x))
            except ValueError:
                pass
        for conf in bundle["conflicts"]:
            v1_ok = _side_present_in_text(conf["value_1"], text, text_floats)
            v2_ok = _side_present_in_text(conf["value_2"], text, text_floats)
            if not (v1_ok and v2_ok):
                errors.append(
                    f"Conflict check failed (R-007) for {conf['investigation_id']} '{conf['field']}': "
                    f"must report both value_1='{conf['value_1']}' ({conf['source_1']}) and "
                    f"value_2='{conf['value_2']}' ({conf['source_2']})."
                )

    # Rule R-006 / R-004: Unknown value / refusal / gap check
    ans_type = bundle.get("answer_type")
    if ans_type == "out_of_scope":
        if not _OUT_OF_SCOPE_RE.search(text):
            errors.append("Refusal check failed (R-004): answer_type is 'out_of_scope' but response does not state it is out of scope.")
    elif ans_type == "no_data":
        if not _NO_DATA_RE.search(text):
            errors.append("Refusal check failed (R-006): answer_type is 'no_data' but response does not state that data is not available in the repository.")
        if bundle.get("gaps"):
            # Ensure at least one key subject/topic from gaps is mentioned
            gap_text = " ".join(bundle["gaps"])
            inv_subjects = bundle.get("investigations") or []
            if inv_subjects and not any(inv.lower() in text.lower() for inv in inv_subjects):
                errors.append(f"Refusal check failed (R-006): response must mention the queried investigation(s) {', '.join(inv_subjects)} and why data is unavailable.")
            elif not inv_subjects and len(gap_text) > 10:
                keywords = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", gap_text)
                            if w.lower() not in {"data", "repository", "corpus", "source", "sources", "unknown", "currently", "contain", "contains"}]
                if keywords and not any(k in text.lower() for k in keywords):
                    errors.append("Refusal check failed (R-006): response does not explain the specific gap from bundle['gaps'].")

    return {
        "passed": len(errors) == 0,
        "errors": errors,
        "citations": valid_cites,
        "hallucinated_citations": hallucinated_cites,
    }


# --- Prompt Builder -----------------------------------------------------------

def _format_bundle_for_prompt(bundle):
    """Serialize only the evidence fields of the bundle for the LLM prompt."""
    allowed = allowed_bundle_ids(bundle)
    cite_examples = []
    for fid in sorted(allowed["F"]):
        cite_examples.append(f"[{fid}]")
    for cid in sorted(allowed["C"]):
        cite_examples.append(f"[{cid}]")
    for pid in sorted(allowed["PSI"]):
        tests = sorted(allowed["PSI_tests"].get(pid, set()))
        if tests:
            for t in tests[:8]:
                cite_examples.append(f"[{pid}:test{t}]")
        else:
            cite_examples.append(f"[{pid}]")
    for sid in sorted(allowed["S"]):
        pages = sorted(allowed["S_pages"].get(sid, set()))
        if pages:
            for p in pages[:5]:
                cite_examples.append(f"[{sid} p.{p}]")
        else:
            cite_examples.append(f"[{sid}]")

    payload = {
        "question": bundle["question"],
        "intent": bundle["intent"],
        "investigations": bundle["investigations"],
        "answer_type": bundle["answer_type"],
        "gaps": bundle["gaps"],
        "facts": bundle["facts"],
        "calculations": bundle["calculations"],
        "conflicts": bundle["conflicts"],
        "test_scan": bundle.get("test_scan"),
        "tests": bundle["tests"],
        "table_rows": bundle["table_rows"],
        "ranking": (bundle.get("ranking") or [])[:10] if bundle.get("ranking") else None,
        "chunks": [
            {
                "source_id": c["source_id"],
                "page": c["page"],
                "section_title": c.get("section_title", ""),
                "investigation_ids": c.get("investigation_ids", []),
                "text": c["text"],
            }
            for c in bundle["chunks"]
        ],
        "rules": bundle["rules"],
    }
    payload = {k: v for k, v in payload.items() if v is not None and v != [] and v != {}}
    return json.dumps(payload, indent=2, ensure_ascii=False), cite_examples


def build_messages(bundle, retry_errors=None, previous_draft=None):
    """Construct system and user messages for the LLM writer."""
    bundle_json, cite_examples = _format_bundle_for_prompt(bundle)
    ans_type = bundle["answer_type"]

    system_prompt = (
        "You are the scientific writer for 'Flames of Aron' (NASA Space Apps 2026 - Flame in Freefall), "
        "a strictly grounded spacecraft fire-safety and microgravity combustion research assistant.\n\n"
        "STRICT RULES YOU MUST FOLLOW:\n"
        "1. LANGUAGE: Write your response in clear, concise, technical English ONLY.\n"
        "2. EVIDENCE BOUNDARY: Use ONLY the facts, numbers, test rows, golden table rows, calculations, conflicts, "
        "and passages provided in the EvidenceBundle JSON. Never use outside knowledge or estimate missing numbers.\n"
        "3. CITATIONS: Cite every factual claim and numerical value in square brackets using ONLY valid IDs from the bundle:\n"
        "   - Challenge facts: [F-005]\n"
        "   - Document chunks or table evidence: [S-007 p.12] or [S-007:12] or [S-007]\n"
        "   - PSI test rows: [PSI-69:test37]\n"
        "   - Verified calculations: [C-001]\n"
        "   NEVER invent or cite any S-XXX, F-XXX, C-XXX, or PSI-XX ID that is not in the bundle.\n"
        "4. ANSWER TYPE ENFORCEMENT (R-004, R-006):\n"
        "   - If `answer_type` is 'out_of_scope': explicitly state that the question is 'out of scope' of the NASA PSI "
        "microgravity combustion repository, explain why using `gaps` and `facts` (citing [F-022] if present), and do NOT speculate.\n"
        "   - If `answer_type` is 'no_data': explicitly state 'Data not available in repository', explain every reason in `gaps` "
        "and relevant `facts` with their citations, and do NOT guess or fabricate measurements.\n"
        "   - If `answer_type` is 'answer': answer the question thoroughly from the bundle, and also mention any relevant `gaps`.\n"
        "5. CONFLICTS (R-007): If `conflicts` is non-empty, you MUST report EVERY conflict entry by presenting BOTH "
        "`value_1` (with its `source_1` ID) AND `value_2` (with its `source_2` ID). Never pick just one value.\n"
        "6. GOLDEN TABLE DRAFT NOTICE (R-008): When reporting values from `table_rows` where `verified` is false, "
        "explicitly mention that the Golden Table is an 'unverified LLM draft'.\n"
        "7. UNKNOWN VALUES (R-006): Keep unknown values as 'unknown'; never replace 'unknown' with 0."
    )

    user_lines = [
        f"ALLOWED CITATION IDS IN THIS BUNDLE: {', '.join(cite_examples) if cite_examples else 'None (medical out-of-scope)'}",
        f"MANDATORY ANSWER_TYPE: {ans_type}",
    ]
    if bundle.get("conflicts"):
        user_lines.append(
            f"MANDATORY CONFLICTS TO REPORT (R-007 - must include BOTH value_1 and value_2 for all {len(bundle['conflicts'])} conflict(s)):\n"
            + "\n".join(
                f"  - {c['investigation_id']} | {c['field']}: value_1='{c['value_1']}' [{c['source_1']}] vs value_2='{c['value_2']}' [{c['source_2']}]"
                for c in bundle["conflicts"]
            )
        )
    user_lines.append("\nEVIDENCE BUNDLE JSON:\n" + bundle_json)
    user_lines.append("\nWrite the final English answer now, strictly obeying all rules and citing only the allowed IDs above.")

    if retry_errors and previous_draft is not None:
        user_lines.append(
            "\n--- VALIDATION FAILED ON YOUR PREVIOUS DRAFT ---\n"
            f"Previous draft:\n{previous_draft}\n\n"
            "Validation errors that you MUST fix:\n"
            + "\n".join(f"- {err}" for err in retry_errors)
            + "\n\nRewrite the complete answer fixing every error above. Remove any citation not in ALLOWED CITATION IDS, "
            "include at least one valid citation from the bundle, and include both values for every conflict."
        )

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "\n".join(user_lines)},
    ]


# --- Main Writer & Pipeline Entrypoints ---------------------------------------

def _build_fallback(bundle, reason, started, retried=False, extra_errors=None):
    text, cites = evidence.evidence_summary(bundle)
    latency = int((time.time() - started) * 1000) if started else 0
    errors = list(extra_errors) if extra_errors else [reason]
    if reason and reason not in errors:
        errors.append(reason)
    return contracts.make_answer(
        bundle,
        "LLM answer not available - showing evidence summary.\n" + text,
        "none/evidence-summary",
        cites,
        latency,
        passed=False,
        errors=errors,
        retried=retried,
        fallback_used=True,
    )


def write_answer(bundle, provider=None, model=None, llm_fn=None, timeout=45):
    """Generate, validate, optionally retry once, and return a validated Answer dict for an EvidenceBundle.

    llm_fn: optional callable(messages) -> str or (str, model_id) for unit testing / custom injection.
    """
    started = time.time()
    contracts.validate_bundle(bundle)

    if llm_fn is None:
        prov, mod, key = resolve_provider_and_key(provider, model)
        if prov == "none" or not key:
            return _build_fallback(bundle, "no LLM configured", started, retried=False)

        def _invoke(msgs):
            return call_llm(msgs, provider=prov, model=mod, api_key=key, timeout=timeout)
    else:
        def _invoke(msgs):
            res = llm_fn(msgs)
            if isinstance(res, tuple) and len(res) == 2:
                return res[0], res[1]
            return str(res), f"{provider or 'mock'}/{model or 'mock-llm'}"

    # Attempt 1
    try:
        msgs1 = build_messages(bundle)
        text1, model_id = _invoke(msgs1)
    except Exception as e:
        return _build_fallback(bundle, f"LLM API error: {e}", started, retried=False)

    val1 = validate_response(text1, bundle)
    if val1["passed"]:
        latency = int((time.time() - started) * 1000)
        return contracts.make_answer(
            bundle,
            text1,
            model_id,
            val1["citations"],
            latency,
            passed=True,
            errors=[],
            retried=False,
            fallback_used=False,
        )

    # Attempt 2 (at most 1 retry with validation feedback)
    try:
        msgs2 = build_messages(bundle, retry_errors=val1["errors"], previous_draft=text1)
        text2, model_id2 = _invoke(msgs2)
    except Exception as e:
        return _build_fallback(
            bundle,
            f"LLM API error on retry: {e}",
            started,
            retried=True,
            extra_errors=val1["errors"],
        )

    val2 = validate_response(text2, bundle)
    if val2["passed"]:
        latency = int((time.time() - started) * 1000)
        return contracts.make_answer(
            bundle,
            text2,
            model_id2,
            val2["citations"],
            latency,
            passed=True,
            errors=[],
            retried=True,
            fallback_used=False,
        )

    # Both attempts failed validation -> deterministic fallback
    combined_errors = list(dict.fromkeys(val1["errors"] + val2["errors"]))
    return _build_fallback(
        bundle,
        "LLM failed validation after retry",
        started,
        retried=True,
        extra_errors=combined_errors,
    )


def answer_question(query, engine, provider=None, model=None, top_k=5, use_llm_router=False, llm_fn=None, timeout=45):
    """End-to-end question answering pipeline for the interface and evaluation scripts.

    1. Builds the deterministic EvidenceBundle (router + tools + hybrid search).
    2. Runs the LLM writer with post-generation validation, 1 retry, and fallback.
    3. Returns a schema-validated Answer dict (contracts.ANSWER_SCHEMA).
    """
    started = time.time()
    classifier = make_llm_classifier(provider=provider, model=model, llm_fn=llm_fn) if use_llm_router else None
    bundle = evidence.build_evidence_bundle(query, engine, top_k=top_k, llm_classify=classifier)
    answer = write_answer(bundle, provider=provider, model=model, llm_fn=llm_fn, timeout=timeout)
    answer["latency_ms"] = max(answer["latency_ms"], int((time.time() - started) * 1000))
    return contracts.validate_answer(answer)


def _print_cli_answer(ans, as_json=False):
    import sys
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    if as_json:
        print(json.dumps(ans, indent=2, ensure_ascii=False))
        return
    b = ans["bundle"]
    v = ans["validation"]
    print("\n" + "=" * 72)
    print(f"Intent      : {b['intent']} (investigations: {b['investigations'] or 'none'})")
    print(f"Answer Type : {ans['answer_type']}")
    print(f"Model       : {ans['model']} ({ans['latency_ms']} ms)")
    print(f"Validation  : passed={v['passed']}, retried={v['retried']}, fallback_used={v['fallback_used']}")
    print(f"Citations   : {', '.join(ans['citations']) if ans['citations'] else 'none'}")
    print("-" * 72)
    print(ans["text"])
    print("=" * 72 + "\n")


if __name__ == "__main__":
    import argparse
    import query_engine

    ap = argparse.ArgumentParser(description="Ask Flames of Aron a spacecraft fire-safety question.")
    ap.add_argument("question", nargs="*", help="Question to ask (omit for interactive loop)")
    ap.add_argument("--provider", default=None, help="LLM provider: gemini, mistral, groq, or none")
    ap.add_argument("--model", default=None, help="LLM model override")
    ap.add_argument("--json", action="store_true", help="Print full Answer JSON object")
    args = ap.parse_args()

    eng = query_engine.CombustionQueryEngine()
    if args.question:
        q = " ".join(args.question).strip()
        _print_cli_answer(answer_question(q, eng, provider=args.provider, model=args.model), as_json=args.json)
    else:
        print("\nFlames of Aron interactive mode (type 'exit' or 'q' to quit):")
        while True:
            try:
                q = input("\nQuestion> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not q or q.lower() in ("exit", "quit", "q"):
                break
            _print_cli_answer(answer_question(q, eng, provider=args.provider, model=args.model), as_json=args.json)

