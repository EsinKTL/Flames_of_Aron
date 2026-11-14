"""
Flames of Aron - Advanced Microgravity Combustion Retrieval & Query Engine
NASA Space Apps Challenge 2026 - Microgravity Combustion & Spacecraft Fire Safety

Features:
- Hybrid Search (BM25Okapi + Dense Embeddings from all-MiniLM-L6-v2)
- Reciprocal Rank Fusion (RRF) with experiment and document filtering
- Structured Golden Table retrieval (physical limits, O2, pressure, flow rate, lunar flags)
- Guardrail Fact verification from facts.yaml
- Strict citation synthesis: [SourceID, Page X]
"""

import os
import re
import json
import pickle
import numpy as np
import pandas as pd
import yaml
from sentence_transformers import SentenceTransformer

from investigations import detect_investigations

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INDEX_DIR = os.path.join(BASE_DIR, "indexes")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
REFERENCE_DIR = os.path.join(BASE_DIR, "reference")

BM25_PATH = os.path.join(INDEX_DIR, "bm25_index.pkl")
DENSE_PATH = os.path.join(INDEX_DIR, "dense_embeddings.npy")
CHUNK_LOOKUP_PATH = os.path.join(INDEX_DIR, "chunk_lookup.json")
ALL_CHUNKS_PATH = os.path.join(INDEX_DIR, "all_chunks_lookup.json")
GOLDEN_TABLE_PATH = os.path.join(PROCESSED_DIR, "golden_table.csv")
GOLDEN_CONFLICTS_PATH = os.path.join(PROCESSED_DIR, "golden_table_conflicts.csv")
GOLDEN_EVIDENCE_PATH = os.path.join(PROCESSED_DIR, "golden_table_evidence.jsonl")
FACTS_PATH = os.path.join(REFERENCE_DIR, "facts.yaml")
MANIFEST_PATH = os.path.join(REFERENCE_DIR, "manifest.csv")

MODEL_NAME = "all-MiniLM-L6-v2"

# --- Conflict matching -------------------------------------------------------
# Question wording -> field family
QUERY_FIELD_FAMILIES = {
    "flow":             r"flow|speed|velocity|cm/s",
    "o2":               r"\bo2\b|oxygen",
    "pressure":         r"pressure|\bpsi\b|\bkpa\b|\batm\b|mmhg",
    "test_count":       r"how many|number of (?:tests|samples|runs)|test count|tests? (?:were )?(?:run|conducted|performed)",
    "operation_period": r"\bwhen\b|\bdates?\b|launch|\byears?\b|\bflew\b|flight period|operation",
    "measurements":     r"radiometer|sensor|measur",
    "burn_time":        r"burn time|duration|how long",
    "fuel_shape_size":  r"thickness|width|length|\bsize\b|dimension",
    "ignition":         r"ignit",
    "name":             r"\bname\b|called",
}
# Conflict-table `field` value -> field family
CONFLICT_FIELD_FAMILIES = {
    "flow":             r"flow",
    "o2":               r"\bo2\b",
    "pressure":         r"pressure",
    "test_count":       r"test_count",
    "operation_period": r"operation_period",
    "measurements":     r"measurements",
    "burn_time":        r"burn time",
    "fuel_shape_size":  r"fuel_shape_size",
    "ignition":         r"ignition",
    "name":             r"^name$",
}
CONFLICT_WORDS_RE = re.compile(r"conflict|disagree|discrepan|inconsisten|different values|which (?:value|one) is (?:right|correct)|sources? (?:differ|say)", re.I)

# --- Atmosphere screening (questions that name no investigation) ------------
SCREENING_RE = re.compile(
    r"\b(?:lunar|moon|habitat|partial pressure|po2|oxygen[- ]enriched|enriched[- ]oxygen|closest|highest|lowest|"
    r"maximum|minimum|which (?:microgravity )?(?:experiments?|tests?|investigations?))\b"
    r"|\d+(?:\.\d+)?\s*%\s*o2|\d+(?:\.\d+)?\s*psi", re.I)
PARTIAL_GRAVITY_RE = re.compile(r"lunar gravity|moon gravity|mars gravity|martian gravity|partial[- ]gravity|reduced gravity|\b\d/\d+\s*-?g\b", re.I)
OUT_OF_SCOPE_RE = re.compile(r"rocket|thruster|propellant|engine fire|re-?entry|heat shield", re.I)
JOINT_FLAG_ORDER = {"yes": 0, "partial": 1, "no": 2, "unknown": 3}


def fmt(value) -> str:
    """Render a golden-table cell; empty / NaN cells become 'unknown' (never 0)."""
    if value is None:
        return "unknown"
    if isinstance(value, float) and np.isnan(value):
        return "unknown"
    text = str(value).strip()
    return text if text and text.lower() != "nan" else "unknown"

def tokenize(text: str):
    """Tokenization matching the indexing pipeline."""
    return re.findall(r"\b[A-Za-z0-9_/%.-]+\b", text.lower())

class CombustionQueryEngine:
    def __init__(self):
        print("Initializing CombustionQueryEngine...")
        
        # 1. Load BM25 Index
        with open(BM25_PATH, "rb") as f:
            data = pickle.load(f)
            self.bm25 = data["bm25"]
            self.tokenized_corpus = data["tokenized_corpus"]
            
        # 2. Load Dense Embeddings
        self.embeddings = np.load(DENSE_PATH)
        self.encoder = SentenceTransformer(MODEL_NAME)
        
        # 3. Load Chunks
        with open(CHUNK_LOOKUP_PATH, "r", encoding="utf-8") as f:
            self.chunks = json.load(f)
            
        with open(ALL_CHUNKS_PATH, "r", encoding="utf-8") as f:
            self.all_chunks = json.load(f)
            
        # 4. Load Golden Table & Conflicts & Evidence
        if os.path.exists(GOLDEN_TABLE_PATH):
            self.golden_df = pd.read_csv(GOLDEN_TABLE_PATH, encoding="utf-8")
        else:
            self.golden_df = pd.DataFrame()

        if os.path.exists(GOLDEN_CONFLICTS_PATH):
            self.conflicts_df = pd.read_csv(GOLDEN_CONFLICTS_PATH, encoding="utf-8")
        else:
            self.conflicts_df = pd.DataFrame()

        if os.path.exists(GOLDEN_EVIDENCE_PATH):
            with open(GOLDEN_EVIDENCE_PATH, "r", encoding="utf-8") as f:
                self.evidence_records = [json.loads(line) for line in f if line.strip()]
        else:
            self.evidence_records = []
            
        # 5. Load Facts YAML
        if os.path.exists(FACTS_PATH):
            with open(FACTS_PATH, "r", encoding="utf-8") as f:
                self.facts_data = yaml.safe_load(f)
        else:
            self.facts_data = {}
            
        # 6. Load Manifest
        if os.path.exists(MANIFEST_PATH):
            self.manifest_df = pd.read_csv(MANIFEST_PATH, encoding="utf-8-sig")
        else:
            self.manifest_df = pd.DataFrame()
            
        print(f"Ready! Corpus: {len(self.chunks)} active chunks, {len(self.golden_df)} Golden Table experiments, {len(self.conflicts_df)} documented conflicts, {len(self.facts_data.get('facts', []))} verified facts.")

    def search_hybrid(self, query: str, top_k: int = 5, experiment_filter=None, category_filter: str = None):
        """
        Executes hybrid search combining BM25 and dense vector cosine similarity via RRF.

        experiment_filter: canonical investigation ID or list of IDs (e.g. "BASS-II", ["FLEX", "FLEX-2"]).
            Matching is exact: "BASS" never returns BASS-II chunks, "FLEX" never returns FLEX-2 chunks.
            The filter is applied BEFORE ranking, so a filtered search always ranks the whole
            filtered subset instead of only the global top-50 candidates.
        category_filter: substring of doc_type (e.g. "results").
        """
        wanted = None
        if experiment_filter:
            wanted = {experiment_filter} if isinstance(experiment_filter, str) else set(experiment_filter)

        allowed = np.ones(len(self.chunks), dtype=bool)
        for idx, chunk in enumerate(self.chunks):
            if wanted is not None and not wanted.intersection(chunk.get("investigation_ids", [])):
                allowed[idx] = False
            elif category_filter and category_filter.lower() not in chunk.get("doc_type", "").lower():
                allowed[idx] = False
        candidates = np.flatnonzero(allowed)
        if candidates.size == 0:
            return []

        # BM25 scores
        q_toks = tokenize(query)
        bm25_scores = self.bm25.get_scores(q_toks)

        # Dense similarity
        q_emb = self.encoder.encode([query], normalize_embeddings=True)[0]
        dense_scores = np.dot(self.embeddings, q_emb)

        # Reciprocal Rank Fusion (k=60) over the allowed subset
        rrf_scores = {}
        top_bm25 = candidates[np.argsort(bm25_scores[candidates])[::-1][:50]]
        top_dense = candidates[np.argsort(dense_scores[candidates])[::-1][:50]]
        for rank, idx in enumerate(top_bm25, start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (0.5 / (60 + rank))
        for rank, idx in enumerate(top_dense, start=1):
            rrf_scores[idx] = rrf_scores.get(idx, 0.0) + (0.5 / (60 + rank))

        results = []
        for idx, score in sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:top_k]:
            chunk = self.chunks[idx]
            results.append({
                "chunk_id": chunk["chunk_id"],
                "source_id": chunk["source_id"],
                "page": chunk.get("page", 1),
                "section_title": chunk.get("section_title", ""),
                "section_type": chunk.get("section_type", ""),
                "investigation_ids": chunk.get("investigation_ids", []),
                "doc_type": chunk.get("doc_type", ""),
                "has_table": chunk.get("has_table", False),
                "rrf_score": float(score),
                "bm25_score": float(bm25_scores[idx]),
                "dense_score": float(dense_scores[idx]),
                "text": chunk["text"]
            })
        return results

    def get_golden_facts(self, query: str):
        """
        Returns Golden Table rows for the investigations explicitly named in the query.
        Uses investigations.detect_investigations (word boundaries + aliases), so
        "BASS-II" returns only the BASS-II row and generic words ("flame", "fabric") match nothing.
        """
        if self.golden_df.empty:
            return []
        ids = detect_investigations(query)
        if not ids:
            return []
        rows = self.golden_df[self.golden_df["id"].isin(ids)]
        return [r.to_dict() for _, r in rows.iterrows()]

    def get_guardrail_facts(self, query: str):
        """
        Retrieves relevant ground truth facts and physical calculation rules from facts.yaml.
        """
        facts = self.facts_data.get("facts", [])
        rules = self.facts_data.get("rules", [])
        calcs = self.facts_data.get("calculations", [])
        
        q_tokens = set(tokenize(query))
        matching_facts = []
        
        for f in facts + calcs:
            topic = str(f.get("topic", "")).lower()
            claim = str(f.get("claim", "")).lower()
            claim_tokens = set(tokenize(topic + " " + claim))
            overlap = q_tokens.intersection(claim_tokens)
            if len(overlap) >= 2 or any(k in topic for k in q_tokens if len(k) > 3):
                matching_facts.append(f)
                
        return matching_facts[:5]

    def get_conflicts(self, query: str, matched_exp_ids: list = None, limit: int = 5):
        """
        Returns documented cross-source conflicts for the investigations named in the query.

        - Investigation match is EXACT (canonical IDs from investigations.detect_investigations
          plus matched_exp_ids); "Saffire-III" never returns Saffire-II rows, "BASS-II" never BASS rows.
        - Rows are ranked by how well their `field` matches what the question asks about
          (flow, O2, pressure, test count, dates ...). Rows with no field match are dropped,
          unless the question explicitly asks about conflicts/discrepancies.
        """
        if self.conflicts_df.empty:
            return []
        ids = set(detect_investigations(query)) | set(matched_exp_ids or [])
        if not ids:
            return []

        asked = {fam for fam, pat in QUERY_FIELD_FAMILIES.items() if re.search(pat, query, re.I)}
        wants_all = bool(CONFLICT_WORDS_RE.search(query))

        scored = []
        for order, (_, row) in enumerate(self.conflicts_df.iterrows()):
            if str(row.get("investigation_id", "")) not in ids:
                continue
            field = str(row.get("field", ""))
            row_fams = {fam for fam, pat in CONFLICT_FIELD_FAMILIES.items() if re.search(pat, field, re.I)}
            score = len(row_fams & asked)
            if score > 0 or wants_all:
                scored.append((-score, order, row.to_dict()))
        scored.sort(key=lambda x: (x[0], x[1]))
        return [r for _, _, r in scored[:limit]]

    def get_rules(self):
        """All agent behaviour rules (R-001 ... R-008). Always included in the context."""
        return list(self.facts_data.get("rules", []))

    def get_screening_rows(self, query: str):
        """
        Compact atmosphere-screening table (all golden-table rows) for questions that ask about
        conditions (lunar habitat, highest O2, 30% O2 / 10.2 psi ...) but name no investigation.
        Not used for partial-gravity or out-of-scope questions.
        Sorted by lunar_joint_flag (yes, partial, no, unknown), then by o2_max descending.
        """
        if self.golden_df.empty or detect_investigations(query):
            return []
        if not SCREENING_RE.search(query) or PARTIAL_GRAVITY_RE.search(query) or OUT_OF_SCOPE_RE.search(query):
            return []
        rows = [r.to_dict() for _, r in self.golden_df.iterrows()]

        def o2max(r):
            try:
                return -float(r.get("o2_max"))
            except (TypeError, ValueError):
                return 1.0  # unknown last within its flag group
        rows.sort(key=lambda r: (JOINT_FLAG_ORDER.get(fmt(r.get("lunar_joint_flag")), 3), o2max(r)))
        return rows

    def build_rag_context(self, query: str, top_k: int = 5):
        """
        Assembles all retrieved evidence into an organized, citation-ready context block.
        """
        inv_ids = detect_investigations(query)

        # 1) Retrieval: investigation filter first, unfiltered fill-up, one chunk per named investigation
        if inv_ids:
            search_results = self.search_hybrid(query, top_k=top_k, experiment_filter=inv_ids)
            seen = {r["chunk_id"] for r in search_results}
            if len(search_results) < top_k:
                for r in self.search_hybrid(query, top_k=top_k * 3):
                    if len(search_results) >= top_k:
                        break
                    if r["chunk_id"] not in seen:
                        search_results.append(r)
                        seen.add(r["chunk_id"])
            for inv in inv_ids:
                if not any(inv in r.get("investigation_ids", []) for r in search_results):
                    for r in self.search_hybrid(query, top_k=1, experiment_filter=inv):
                        if r["chunk_id"] not in seen:
                            search_results.append(r)
                            seen.add(r["chunk_id"])
            filter_applied = list(inv_ids)
        else:
            search_results = self.search_hybrid(query, top_k=top_k)
            filter_applied = []

        golden_matches = self.get_golden_facts(query)
        screening_rows = self.get_screening_rows(query)
        guardrails = self.get_guardrail_facts(query)
        rules = self.get_rules()
        matched_exp_ids = [m.get("id") for m in golden_matches if m.get("id")]
        conflicts = self.get_conflicts(query, matched_exp_ids=matched_exp_ids)

        context_parts = []

        # 0. Agent rules (always)
        if rules:
            context_parts.append("### AGENT RULES (MUST FOLLOW):")
            for r in rules:
                context_parts.append(f"- [{r.get('id')}] {r.get('rule')}")
            context_parts.append("")

        # 1. Guardrail Facts
        if guardrails:
            context_parts.append("### AUTHORITATIVE NASA BASELINE FACTS & PHYSICAL CONSTANTS:")
            for g in guardrails:
                context_parts.append(f"- [{g.get('id', 'F')}] ({g.get('topic')}) {g.get('claim')} [Source: {g.get('source')}]")
            context_parts.append("")

        # 2. Golden Table Parameters (investigations named in the question)
        if golden_matches:
            context_parts.append("### GOLDEN TABLE EXPERIMENT SPECIFICATIONS (unverified LLM draft unless 'verified: yes'):")
            for m in golden_matches:
                context_parts.append(f"**Experiment: {fmt(m.get('name'))} (ID: {fmt(m.get('id'))})**")
                context_parts.append(f"- Category: {fmt(m.get('category'))} | Fuel: {fmt(m.get('fuel_type'))} ({fmt(m.get('fuel_material'))}; {fmt(m.get('fuel_shape_size'))})")
                context_parts.append(f"- Oxygen (mole fraction): {fmt(m.get('o2_min'))} - {fmt(m.get('o2_max'))} | raw: {fmt(m.get('o2_raw'))} | note: {fmt(m.get('o2_note'))}")
                context_parts.append(f"- Total pressure (psi): {fmt(m.get('pressure_psi_min'))} - {fmt(m.get('pressure_psi_max'))} | raw: {fmt(m.get('pressure_raw'))} | note: {fmt(m.get('pressure_note'))}")
                context_parts.append(f"- Flow (cm/s): {fmt(m.get('flow_cm_s_min'))} - {fmt(m.get('flow_cm_s_max'))} | raw: {fmt(m.get('flow_raw'))} | note: {fmt(m.get('flow_note'))}")
                context_parts.append(f"- Gravity regime: {fmt(m.get('gravity_regime'))} | Hardware: {fmt(m.get('hardware'))}")
                context_parts.append(f"- Lunar flags: O2>=0.30: {fmt(m.get('lunar_o2_flag'))} | P<=10.2 psi: {fmt(m.get('lunar_pressure_flag'))} | same test (joint): {fmt(m.get('lunar_joint_flag'))}")
                context_parts.append(f"- Lunar note: {fmt(m.get('lunar_note'))}")
                context_parts.append(f"- Key Finding: {fmt(m.get('main_finding'))}")
                context_parts.append(f"- Evidence level: {fmt(m.get('evidence_level'))} | verified: {fmt(m.get('verified'))} | conflicts on record: {fmt(m.get('has_conflict'))}")
                context_parts.append(f"- Citations: {fmt(m.get('pages'))}")
                context_parts.append("")

        # 2a. Atmosphere screening table (condition questions that name no investigation)
        if screening_rows:
            context_parts.append("### ATMOSPHERE SCREENING TABLE (all core investigations; unverified LLM draft):")
            context_parts.append("Lunar target: O2 >= 0.30 AND total pressure <= 10.2 psi IN THE SAME TEST [F-005]. "
                                 "Use lunar_joint_flag and lunar_note; never infer a match from range end points "
                                 "(po2 values are products of range end points, not single tests).")
            context_parts.append("| id | O2 min-max | P psi min-max | O2 flag | P flag | joint | evidence | lunar note | citations |")
            for m in screening_rows:
                context_parts.append(
                    f"| {fmt(m.get('id'))} | {fmt(m.get('o2_min'))}-{fmt(m.get('o2_max'))} | "
                    f"{fmt(m.get('pressure_psi_min'))}-{fmt(m.get('pressure_psi_max'))} | {fmt(m.get('lunar_o2_flag'))} | "
                    f"{fmt(m.get('lunar_pressure_flag'))} | {fmt(m.get('lunar_joint_flag'))} | {fmt(m.get('evidence_level'))} | "
                    f"{fmt(m.get('lunar_note'))} | {fmt(m.get('pages'))} |")
            context_parts.append("")

        # 2b. Documented Source Conflicts
        if conflicts:
            context_parts.append("### DOCUMENTED CROSS-SOURCE CONFLICTS (present BOTH values, rule R-007):")
            for c in conflicts:
                context_parts.append(
                    f"- [{c.get('investigation_id')} | {c.get('field')}] "
                    f"Value 1: {c.get('value_1')} ({c.get('source_1')}) vs "
                    f"Value 2: {c.get('value_2')} ({c.get('source_2')}) -> "
                    f"Chosen in table: {c.get('chosen')} ({c.get('rationale')})"
                )
            context_parts.append("")

        # 3. Microgravity Literature Chunks
        context_parts.append("### RETRIEVED RESEARCH PASSAGES & EXPERIMENT TABLES:")
        for idx, res in enumerate(search_results, start=1):
            source_tag = f"[{res['source_id']}, Page {res['page']}]"
            context_parts.append(f"--- [Passage {idx} | Source: {source_tag} | Score: {res['rrf_score']:.4f}] ---")
            context_parts.append(res["text"])
            context_parts.append("")

        return {
            "query": query,
            "assembled_context": "\n".join(context_parts),
            "investigation_ids": inv_ids,
            "filter_applied": filter_applied,
            "search_results": search_results,
            "golden_matches": golden_matches,
            "screening_rows": screening_rows,
            "conflicts": conflicts,
            "guardrails": guardrails,
            "rules": rules,
        }

if __name__ == "__main__":
    engine = CombustionQueryEngine()
    test_q = "How does forced air flow affect PMMA flammability in BASS-II compared to normal gravity?"
    res = engine.build_rag_context(test_q, top_k=3)
    print("\n" + "="*70)
    print("QUERY:", res["query"])
    print("="*70)
    print(res["assembled_context"][:2000])
    print("...")
