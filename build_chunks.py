import os
import re
import json
import zipfile
import xml.etree.ElementTree as ET
import unicodedata
import pdfplumber
import pypdf
import docx

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RAW_DOCS_DIR = os.path.join(BASE_DIR, "raw", "docs")
RAW_PSI_DIR = os.path.join(BASE_DIR, "raw", "psi")
INTERIM_DIR = os.path.join(BASE_DIR, "interim")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
EVAL_DIR = os.path.join(BASE_DIR, "evaluation")
MANIFEST_PATH = os.path.join(BASE_DIR, "reference", "manifest.csv")

for d in [INTERIM_DIR, PROCESSED_DIR, LOGS_DIR, EVAL_DIR]:
    os.makedirs(d, exist_ok=True)

# Belge Kayıt ve Metadata Haritası (manifest.csv ile %100 Birebir Eşleşen Resmi Kaynak ID'leri)
DOC_REGISTRY = {
    # BASS / BASS-II
    "Detailed Results BAS-2.pdf": {
        "source_id": "S-007",
        "doc_title": "NASA/TM-20210011385 BASS-II Summary Report",
        "investigation_ids": ["BASS-II"],
        "doc_type": "results",
        "year": 2021,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-2 Engineering Requirements.pptx": {
        "source_id": "S-008",
        "doc_title": "BASS-2 Engineering Requirements",
        "investigation_ids": ["BASS-II"],
        "doc_type": "design",
        "year": 2010,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20140011099.pdf": {
        "source_id": "S-002",
        "doc_title": "Thickness and Fuel Preheating Effects on Material Flammability (BASS)",
        "investigation_ids": ["BASS"],
        "doc_type": "results",
        "year": 2014,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20150008961.pdf": {
        "source_id": "S-003",
        "doc_title": "Microgravity Flammability of PMMA Rods in Concurrent Flow",
        "investigation_ids": ["BASS-II"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20150008962.pdf": {
        "source_id": "S-004",
        "doc_title": "Concurrent Flame Growth, Spread and Extinction over Composite Fabric (BASS)",
        "investigation_ids": ["BASS", "BASS-II"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20160000593.pdf": {
        "source_id": "S-005",
        "doc_title": "Combustion of Solids in Microgravity: Results from BASS-II",
        "investigation_ids": ["BASS-II"],
        "doc_type": "results",
        "year": 2016,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20205004657.pdf": {
        "source_id": "S-006",
        "doc_title": "Effects of Confinement on Flame Spread in Microgravity",
        "investigation_ids": ["BASS-II"],
        "doc_type": "results",
        "year": 2020,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-II Procedure.docx": {
        "source_id": "S-009",
        "doc_title": "BASS Ops with Reduced O2 Partial Pressure & Procedure",
        "investigation_ids": ["BASS-II"],
        "doc_type": "design",
        "year": 2014,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-II data FAQ.docx": {
        "source_id": "S-010",
        "doc_title": "BASS-II Data FAQ and PI Test Matrix Guide",
        "investigation_ids": ["BASS-II"],
        "doc_type": "overview",
        "year": 2017,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-II_SRD.pdf": {
        "source_id": "S-011",
        "doc_title": "Science Requirements Document (SRD) for BASS-II",
        "investigation_ids": ["BASS-II", "SPICE"],
        "doc_type": "design",
        "year": 2013,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_SRD.pdf": {
        "source_id": "S-012",
        "doc_title": "Science Requirements Document (SRD) for BASS",
        "investigation_ids": ["BASS", "SPICE"],
        "doc_type": "design",
        "year": 2010,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },

    # FLEX / FLEX-2 / CFI
    "Detailed Results FLEX.pdf": {
        "source_id": "S-013",
        "doc_title": "NASA/TP-2015-216046 Detailed Results from FLEX",
        "investigation_ids": ["FLEX"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "20150018397.pdf": {
        "source_id": "S-014",
        "doc_title": "Combustion Characteristics in Cool-Flame Regime of n-Heptane (CFI / FLEX)",
        "investigation_ids": ["FLEX", "CFI"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "FLEX_20090014812.pdf": {
        "source_id": "S-015",
        "doc_title": "Multi-User Droplet Combustion Apparatus - FLEX Hardware",
        "investigation_ids": ["FLEX"],
        "doc_type": "overview",
        "year": 2009,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "FLEX_20130014061.pdf": {
        "source_id": "S-016",
        "doc_title": "Methanol Droplet Combustion in Oxygen-Inert Environments (FLEX)",
        "investigation_ids": ["FLEX"],
        "doc_type": "results",
        "year": 2013,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },

    # Saffire
    "SAFFIRE-I and SAFFIRE-III DoD.docx": {
        "source_id": "S-017",
        "doc_title": "Saffire-I and Saffire-III Description of Data (DoD) & Operations",
        "investigation_ids": ["Saffire-I", "Saffire-III"],
        "doc_type": "overview",
        "year": 2018,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "SAFFIRE_Offgassing_Testing_Strategy.pdf": {
        "source_id": "S-018",
        "doc_title": "SAFFIRE Offgassing Testing Strategy",
        "investigation_ids": ["Saffire-I"],
        "doc_type": "design",
        "year": 2015,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "SFSDP-VIS-0295_Saffire 1 and 3_Thermocouple Placement.pdf": {
        "source_id": "S-019",
        "doc_title": "Saffire-I and Saffire-III Thermocouple Placement and Sensor Layout",
        "investigation_ids": ["Saffire-I", "Saffire-III"],
        "doc_type": "design",
        "year": 2016,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20170000230.pdf": {
        "source_id": "S-020",
        "doc_title": "Operation and Development Status of the Spacecraft Fire Experiments (Saffire)",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "overview",
        "year": 2016,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20170001636.pdf": {
        "source_id": "S-021",
        "doc_title": "The Spacecraft Fire Experiment (Saffire) - Objectives, Development and Status",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "overview",
        "year": 2016,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20180005168.pdf": {
        "source_id": "S-022",
        "doc_title": "Saffire: A Novel Approach to Study of Spacecraft Fire Safety (Saffire I-III Results)",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "results",
        "year": 2017,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20220002714.pdf": {
        "source_id": "S-023",
        "doc_title": "Model Development of Large-Scale Spacecraft Fires During Saffire Experiments",
        "investigation_ids": ["Saffire-IV"],
        "doc_type": "results",
        "year": 2022,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },

    # Overview & Programmatic
    "20030002834.pdf": {
        "source_id": "S-024",
        "doc_title": "New Technology for FireAttire (Spacecraft Fire Safety & Materials)",
        "investigation_ids": ["Earth applications"],
        "doc_type": "overview",
        "year": 2003,
        "hardware": "MSG / CIR",
        "fuel_phase": "solid"
    },
    "nasa.pdf": {
        "source_id": "S-025",
        "doc_title": "NASA Microgravity Combustion Program Overview",
        "investigation_ids": ["General"],
        "doc_type": "overview",
        "year": 2015,
        "hardware": "MSG / CIR",
        "fuel_phase": "multi-phase"
    },
    "np-2015-10-034-jsc_combustion_in_reduced_gravity-iss-mini-book-011116-508.pdf": {
        "source_id": "S-026",
        "doc_title": "NASA ISS Research Mini-Book: Combustion in Reduced Gravity",
        "investigation_ids": ["General"],
        "doc_type": "overview",
        "year": 2015,
        "hardware": "MSG / CIR",
        "fuel_phase": "multi-phase"
    }
}

PROTECTED_HYPHENS = {
    "BASS-I", "BASS-II", "Saffire-I", "Saffire-II", "Saffire-III", "Saffire-IV", "Saffire-V", "Saffire-VI",
    "FLEX-2", "CFI-G", "E-FIELD", "SAME-R", "DAFT-2", "STDCE-1", "s-Flame", "n-heptane", "n-alkane",
    "co-flow", "Co-flow", "opposed-flow", "Opposed-flow", "concurrent-flow", "Concurrent-flow",
    "micro-gravity", "low-gravity", "reduced-gravity", "normal-gravity", "partial-gravity",
    "two-sided", "one-sided", "pre-breathe", "fine-water-mist", "Fine-Water-Mist", "NASA-STD-6001"
}

PROTECTED_HYPHENS_LOWER = {p.lower() for p in PROTECTED_HYPHENS}

NUMERIC_COND_REGEX = re.compile(
    r"(\b\d+(?:[\.,]\d+)?\s*(?:%\s*O2|%\s*oxygen|psi|psia|kPa|atm|mmHg|cm/s|mm/s|m/s|W\b|ppm|micron|μm|\bmm\b|\bcm\b))",
    re.IGNORECASE
)

HEADER_NOISE_PATTERNS = [
    re.compile(r"^\s*NASA/(?:TM|TP|CR)[—\-–]\d{4}[—\-–]?\d+\s*\d*\s*$", re.MULTILINE),
    re.compile(r"^\s*Page\s+\d+\s*(?:of\s+\d+)?\s*$", re.MULTILINE | re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$", re.MULTILINE)
]

SECTION_PATTERNS = [
    (re.compile(r"\b(?:abstract|executive\s+summary|summary)\b", re.I), "objective"),
    (re.compile(r"\b(?:introduction|background|objective|objectives|motivation)\b", re.I), "objective"),
    (re.compile(r"\b(?:experimental\s+setup|hardware|apparatus|procedure|procedures|methodology|approach|experiment\s+description|diagnostics)\b", re.I), "methodology"),
    (re.compile(r"\b(?:test\s+matrix|test\s+conditions|experimental\s+matrix|operating\s+conditions)\b", re.I), "conditions"),
    (re.compile(r"\b(?:results|observations|discussion|data\s+analysis|findings|combustion\s+products|flammability\s+boundary)\b", re.I), "results"),
    (re.compile(r"\b(?:conclusions|concluding\s+remarks|summary\s+of\s+results)\b", re.I), "results"),
    (re.compile(r"\b(?:references|bibliography|publications\s+resulting|papers\s+and\s+presentations)\b", re.I), "references"),
]

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
    for pat in HEADER_NOISE_PATTERNS:
        text = pat.sub("", text)

    def fix_hyphen(match):
        full = match.group(0).replace("\n", "").replace(" ", "")
        if full.lower() in PROTECTED_HYPHENS_LOWER:
            return full  # kaynaktaki yazımı koru (set sırası çıktıyı değiştirmesin)
        w1, w2 = match.group(1), match.group(2)
        if w2 and w2[0].islower() and not w1.isupper():
            return w1 + w2
        return w1 + "-" + w2

    text = re.sub(r"([A-Za-z0-9]+)-\s*\n\s*([A-Za-z0-9]+)", fix_hyphen, text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def extract_page_prose_column_aware(page, table_bboxes):
    """
    1) Tablo kutularının (table_bboxes) içindeki karakterleri filtreler (tablo metni düz metinle çiftlenmesin diye).
    2) İki sütunlu düzeni (Two-column layout) otomatik algılar ve okuma sırasını (Üst Başlık -> Sol Sütun -> Sağ Sütun) korur.
    """
    filtered_page = page
    for bbox in table_bboxes:
        # Tablo alanı dışındaki bölgeleri tut
        x0, top, x1, bottom = bbox
        filtered_page = filtered_page.filter(
            lambda obj, bx0=x0, btop=top, bx1=x1, bbot=bottom: not (
                obj.get("x0", 0) >= bx0 - 2 and obj.get("x1", 0) <= bx1 + 2 and
                obj.get("top", 0) >= btop - 2 and obj.get("bottom", 0) <= bbot + 2
            )
        )

    words = filtered_page.extract_words()
    if not words:
        return ""

    mid = page.width / 2.0
    # Sayfa ortasındaki 6pt'lik olası sütun boşluğuna (gutter: [mid - 3, mid + 3]) değen kelimeleri bul
    gutter_words = [
        w for w in words
        if w["x0"] < mid + 3 and w["x1"] > mid - 3 and w["top"] < page.height * 0.88
    ]
    
    # Eğer sayfanın alt yarısında (top >= page.height * 0.50) orta boşluğa değen çok sayıda kelime varsa (> 3),
    # bu sayfa TEK SÜTUNLUDUR (kesinlikle ikiye bölünmemelidir).
    bottom_half_gutter_words = [w for w in gutter_words if w["top"] >= page.height * 0.50]
    if len(bottom_half_gutter_words) > 3:
        return filtered_page.extract_text() or ""

    # Üstteki tam genişlikli başlık/özet bloğunun bittiği Y koordinatını bul
    split_y = 0.0
    for gw in gutter_words:
        if gw["top"] < page.height * 0.55:
            split_y = max(split_y, gw["bottom"] + 2)

    lower_words = [w for w in words if w["top"] >= split_y and w["bottom"] < page.height * 0.90]
    lower_gutter = [w for w in lower_words if w["x0"] < mid + 3 and w["x1"] > mid - 3]
    left_w = [w for w in lower_words if w["x1"] <= mid + 3]
    right_w = [w for w in lower_words if w["x0"] >= mid - 3]

    # Gerçek iki sütunlu düzen: Alt gövdede hem sol hem sağ sütunda >40 kelime var ve orta olukta (gutter) <= 2 kelime var
    if len(left_w) > 40 and len(right_w) > 40 and len(lower_gutter) <= 2:
        parts = []
        if split_y > 10:
            top_txt = filtered_page.crop((0, 0, page.width, split_y)).extract_text() or ""
            if top_txt.strip():
                parts.append(top_txt.strip())
        left_txt = filtered_page.crop((0, split_y, mid + 2, page.height)).extract_text() or ""
        right_txt = filtered_page.crop((mid - 2, split_y, page.width, page.height)).extract_text() or ""
        if left_txt.strip():
            parts.append(left_txt.strip())
        if right_txt.strip():
            parts.append(right_txt.strip())
        return "\n\n".join(parts)

    return filtered_page.extract_text() or ""

# --- Satır düzeyinde başlık tespiti -------------------------------------------
# Öncelik sırası önemlidir: "Summary of Results" -> results, "Experimental Results" -> results.
HEADING_PRIORITY = [
    ("references",  r"references|bibliography|works cited|papers and presentations|publications(?: resulting)?|acknowledge?ments?"),
    ("results",     r"conclusions?|concluding remarks|summary of results|summary and conclusions?"),
    ("results",     r"results?|discussion|observations|findings|data analysis|analysis"),
    ("conditions",  r"test matrix|test matrices|test conditions|experimental conditions|operating conditions|test parameters|test plan|flight matrix|conditions"),
    ("methodology", r"experimental (?:setup|set-up|apparatus|hardware|methods?|approach|description|design|procedures?|details)|experiment description|hardware|apparatus|procedures?|methods?|methodology|approach|diagnostics|instrumentation|materials|sample preparation|facility"),
    ("objective",   r"abstract|executive summary|summary|introduction|background|objectives?|motivation|overview|purpose"),
]
HEADING_NUM_RE = re.compile(r"^(?:\d{1,2}(?:\.\d{1,2}){0,3}\.?|[IVX]{1,5}\.|[A-H]\.|Appendix\s+[A-Z0-9]+[.:]?)\s+")

def heading_section(line: str):
    """Satır bir bölüm başlığıysa (section_type, başlık) döndürür, değilse None."""
    l = line.strip()
    if not (3 <= len(l) <= 75):
        return None
    m = HEADING_NUM_RE.match(l)
    body = (l[m.end():] if m else l).strip().rstrip(":").strip()
    words = body.split()
    if not words or len(words) > (8 if m else 6):
        return None
    if re.search(r"[.;,]$", body) or re.search(r"\d{2,}", body) or not body[0].isalpha():
        return None
    long_words = [w for w in words if len(w) > 3]
    titleish = body.isupper() or not long_words or (
        sum(w[0].isupper() for w in long_words) / len(long_words) >= 0.5)
    if not titleish or not words[0][0].isupper():
        return None
    low = body.lower()
    if not m:
        # Numarasız satırda anahtar sözcük başta olmalı ("Results show ..." gibi cümleleri ele)
        for sec_type, pat in HEADING_PRIORITY:
            if re.match(rf"(?:{pat})\b", low):
                return sec_type, l[:80]
        # "Experimental Results", "Flame Spread Results": kısa ve tamamen başlık biçiminde
        strict = body.isupper() or (long_words and all(w[0].isupper() for w in long_words))
        if strict and len(words) <= 4:
            for sec_type, pat in HEADING_PRIORITY:
                if re.search(rf"\b(?:{pat})\b", low):
                    return sec_type, l[:80]
        return None
    for sec_type, pat in HEADING_PRIORITY:
        if re.search(rf"\b(?:{pat})\b", low):
            return sec_type, l[:80]
    return None

def split_sections(text_block: str, current_section_type: str, current_section_title: str):
    """Sayfa metnini bölüm başlıklarından böler: [(section_type, section_title, metin), ...].
    Başlıktan önceki kısım bir önceki sayfanın bölümünü sürdürür."""
    segments = []
    buf = []
    cur_t, cur_ti = current_section_type, current_section_title
    for line in text_block.split("\n"):
        h = heading_section(line)
        if h:
            if "\n".join(buf).strip():
                segments.append((cur_t, cur_ti, "\n".join(buf).strip()))
            buf = []
            cur_t, cur_ti = h
        buf.append(line)
    if "\n".join(buf).strip():
        segments.append((cur_t, cur_ti, "\n".join(buf).strip()))
    return segments or [(cur_t, cur_ti, text_block)]

def detect_section(text_block: str, current_section_type: str, current_section_title: str):
    lines = [l.strip() for l in text_block.split("\n") if l.strip()]
    for line in lines[:8]:
        if len(line) < 95:
            if re.match(r"^(?:\d+\.\d*(?:\.\d+)?|[IVX]+\.|Appendix\s+[A-Z]|Abstract|Executive\s+Summary|Introduction|Conclusions|References|Acknowledgments|Summary)\b", line, re.I):
                for pat, sec_type in SECTION_PATTERNS:
                    if pat.search(line):
                        return sec_type, line[:80]
    return current_section_type, current_section_title

def format_table_markdown(table_rows):
    if not table_rows or len(table_rows) < 2:
        return None, None
    cleaned_rows = []
    for row in table_rows:
        if not row:
            continue
        cells = [re.sub(r"\s+", " ", str(c or "")).strip() for c in row]
        if any(cells):
            cleaned_rows.append(cells)
    if len(cleaned_rows) < 2:
        return None, None
    header = cleaned_rows[0]
    col_count = len(header)
    if col_count < 2:
        return None, None
    header_line = "| " + " | ".join(header) + " |"
    sep_line = "| " + " | ".join(["---"] * col_count) + " |"
    body_lines = []
    for r in cleaned_rows[1:]:
        padded = (r + [""] * col_count)[:col_count]
        body_lines.append("| " + " | ".join(padded) + " |")
    return header_line + "\n" + sep_line, body_lines

def estimate_tokens(text: str) -> int:
    words = len(text.split())
    chars_est = len(text) // 4
    return max(words, chars_est)

def split_into_chunks(text: str, target_tokens: int = 400, overlap_tokens: int = 55):
    sentences = re.split(r"(?<=[.!?])\s+|\n\n+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    chunks = []
    current_sents = []
    current_toks = 0

    for sent in sentences:
        s_toks = estimate_tokens(sent)
        if current_toks + s_toks > target_tokens and current_sents:
            chunks.append(" ".join(current_sents))
            overlap_sents = []
            ov_toks = 0
            for prev_s in reversed(current_sents):
                pt = estimate_tokens(prev_s)
                if ov_toks + pt <= overlap_tokens or not overlap_sents:
                    overlap_sents.insert(0, prev_s)
                    ov_toks += pt
                else:
                    break
            current_sents = overlap_sents
            current_toks = ov_toks

        current_sents.append(sent)
        current_toks += s_toks

    if current_sents:
        chunks.append(" ".join(current_sents))
    return chunks

def refine_investigation_ids(doc_investigations: list, text: str, section_title: str, source_id: str) -> list:
    """
    Refines document-level experiment tags down to chunk-level specific tags using regex.
    - Single-experiment documents keep their single tag cleanly (no cross-pollution).
    - Multi-experiment documents narrow down to the subset of doc_investigations mentioned in the chunk.
    - Overview documents (General, e.g. S-025, S-026) map to specific experiments discussed in the chunk.
    """
    full_ctx = (section_title + " " + text).lower()

    # Case 1: Overview documents (General -> S-025, S-026 Mini-book)
    if doc_investigations == ["General"]:
        detected = []
        if re.search(r'\bbass[- ]?ii\b|\bbass[- ]?2\b', full_ctx):
            detected.append("BASS-II")
        elif re.search(r'\bbass\b', full_ctx):
            detected.append("BASS")
            
        if re.search(r'\bflex[- ]?2\b|\bflex[- ]?ii\b', full_ctx):
            detected.append("FLEX-2")
        elif re.search(r'\bflex\b|\bdroplet combustion\b', full_ctx):
            detected.append("FLEX")
            
        if re.search(r'\bsame[- ]?r\b|\bsame[- ]?2\b', full_ctx):
            detected.append("SAME-R")
        elif re.search(r'\bsame\b|\bsmoke aerosol\b', full_ctx):
            detected.append("SAME")
            
        if re.search(r'\bdaft\b|\bdust aerosol\b', full_ctx):
            detected.append("DAFT")
            
        if re.search(r'\bsaffire[- ]?iii\b|\bsaffire[- ]?3\b', full_ctx):
            detected.append("Saffire-III")
        elif re.search(r'\bsaffire[- ]?ii\b|\bsaffire[- ]?2\b', full_ctx):
            detected.append("Saffire-II")
        elif re.search(r'\bsaffire\b', full_ctx):
            detected.append("Saffire-I")
            
        if re.search(r'\bcfi[- ]?g\b|\bacme[- ]?cfi\b', full_ctx):
            detected.append("ACME-CFI-G")
        elif re.search(r'\bcfi\b|cool flames? investigation', full_ctx):
            detected.append("CFI")
            
        if re.search(r'\bbre\b|\bburning rate emulator\b', full_ctx):
            detected.append("ACME-BRE")
            
        if re.search(r'\bspice\b', full_ctx):
            detected.append("SPICE")
            
        if re.search(r'\bslice\b', full_ctx):
            detected.append("SLICE")
            
        if detected:
            return list(dict.fromkeys(detected))
        return ["General"]

    # Case 2: Single-experiment document -> already clean, return as-is
    if len(doc_investigations) == 1:
        return doc_investigations

    # Case 3: Multi-experiment document -> narrow strictly within doc_investigations
    allowed = set(doc_investigations)

    # 3a: BASS / BASS-II / SPICE
    if any("BASS" in inv for inv in doc_investigations):
        matched = []
        has_b2 = bool(re.search(r'\bbass[- ]?ii\b|\bbass[- ]?2\b|\bbass 2\b', full_ctx))
        has_b1 = bool(re.search(r'\bbass[- ]?i\b|\bbass[- ]?1\b|\bbass 1\b', full_ctx))
        has_spice = bool(re.search(r'\bspice\b', full_ctx))

        if "BASS" in allowed and "BASS-II" in allowed:
            if has_b2 and not has_b1:
                matched.append("BASS-II")
            elif has_b1 and not has_b2:
                matched.append("BASS")
            elif has_b1 and has_b2:
                matched.extend(["BASS", "BASS-II"])
            else:
                matched.append("BASS-II")
        else:
            if "BASS-II" in allowed:
                matched.append("BASS-II")
            elif "BASS" in allowed:
                matched.append("BASS")

        if "SPICE" in allowed and has_spice:
            matched.append("SPICE")
        return matched if matched else [doc_investigations[0]]

    # 3b: Saffire multi-experiment docs (S-017, S-020, S-021, S-022)
    if any("Saffire" in inv for inv in doc_investigations):
        s_matches = []
        if "Saffire-I" in allowed and re.search(r'\bsaffire[- ]?i\b|\bsaffire[- ]?1\b|\bsaffire 1\b|\bi-[12]\b', full_ctx):
            s_matches.append("Saffire-I")
        if "Saffire-II" in allowed and re.search(r'\bsaffire[- ]?ii\b|\bsaffire[- ]?2\b|\bsaffire 2\b|\b2-[1-9]\b', full_ctx):
            s_matches.append("Saffire-II")
        if "Saffire-III" in allowed and re.search(r'\bsaffire[- ]?iii\b|\bsaffire[- ]?3\b|\bsaffire 3\b|\biii-[12]\b', full_ctx):
            s_matches.append("Saffire-III")
        if s_matches:
            return s_matches
        return doc_investigations

    # 3c: FLEX / CFI (S-014)
    if "FLEX" in allowed and "CFI" in allowed:
        f_matches = []
        # "cool flame" FLEX'in kendi bulgusudur; CFI yalnızca açıkça anılırsa etiketlenir
        if re.search(r'\bcfi\b(?![- ]?g\b)|cool flames? investigation(?! with gases)', full_ctx):
            f_matches.append("CFI")
        if re.search(r'\bflex[- ]?2\b|\bflex[- ]?ii\b', full_ctx):
            f_matches.append("FLEX-2")
        if re.search(r'\bflex\b(?![- ]?(?:2|ii)\b)', full_ctx):
            f_matches.append("FLEX")
        return f_matches if f_matches else doc_investigations

    return doc_investigations

def update_manifest_chunk_counts(all_chunks, manifest_path=MANIFEST_PATH):
    """Write the number of chunks per source into manifest.csv `chunk_count`.

    Only the chunk_count column changes. Encoding (UTF-8 with BOM), CRLF line endings and
    column order are preserved. Sources without chunks get "" (not 0), so "not chunked"
    is never confused with "chunked to nothing". Returns the number of changed rows.
    """
    import csv
    from collections import Counter
    counts = Counter(c["source_id"] for c in all_chunks)
    with open(manifest_path, "rb") as fb:
        raw = fb.read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    with open(manifest_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fields = reader.fieldnames
        rows = list(reader)
    changed = 0
    for r in rows:
        new = str(counts[r["source_id"]]) if counts.get(r["source_id"]) else ""
        if r.get("chunk_count", "") != new:
            r["chunk_count"] = new
            changed += 1
    unknown = set(counts) - {r["source_id"] for r in rows}
    if unknown:
        raise ValueError(f"chunks reference source_ids missing from manifest: {sorted(unknown)}")
    with open(manifest_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, lineterminator=newline)
        w.writeheader()
        w.writerows(rows)
    return changed

def main():
    interim_pages_path = os.path.join(INTERIM_DIR, "pages.jsonl")
    chunks_output_path = os.path.join(PROCESSED_DIR, "chunks.jsonl")
    
    all_pages_records = []
    all_chunks = []
    stats = {
        "total_docs": 0,
        "total_pages": 0,
        "text_chunks": 0,
        "table_chunks": 0,
        "caption_chunks_filtered": 0,
        "ref_chunks_tagged": 0
    }

    doc_files = []
    for root, _, files in os.walk(RAW_DOCS_DIR):
        for f in sorted(files):
            if f.lower().endswith((".pdf", ".docx", ".pptx")):
                doc_files.append(os.path.join(root, f))

    print(f"Toplam {len(doc_files)} belge bulundu. İşleniyor...")

    for fpath in doc_files:
        fname = os.path.basename(fpath)
        if os.path.getsize(fpath) < 100:
            continue

        meta = DOC_REGISTRY.get(fname, {
            "source_id": "S-999",
            "doc_title": fname,
            "investigation_ids": ["General"],
            "doc_type": "overview",
            "year": 2020,
            "hardware": "MSG / CIR",
            "fuel_phase": "solid"
        })

        source_id = meta["source_id"]
        inv_str = ", ".join(meta["investigation_ids"])
        doc_title = meta["doc_title"]
        stats["total_docs"] += 1
        print(f"  -> [{source_id}] {fname} işleniyor...")

        if fname.lower().endswith(".pptx"):
            try:
                with zipfile.ZipFile(fpath, "r") as z:
                    slide_files = sorted(
                        [f for f in z.namelist() if re.match(r"ppt/slides/slide\d+\.xml", f)],
                        key=lambda x: int(re.findall(r"\d+", x)[0])
                    )
                    for s_idx, sf in enumerate(slide_files, start=1):
                        stats["total_pages"] += 1
                        root = ET.fromstring(z.read(sf))
                        paras = []
                        for p in root.iter():
                            if p.tag.endswith("}p"):
                                line = "".join(t.text for t in p.iter() if t.tag.endswith("}t") and t.text).strip()
                                if line:
                                    paras.append(line)
                        slide_text = clean_text("\n".join(paras))
                        if len(slide_text) < 40:
                            continue
                        sec_title = paras[0] if paras else f"Slide {s_idx}"
                        all_pages_records.append({
                            "source_id": source_id,
                            "filename": fname,
                            "page": s_idx,
                            "section_type": "methodology",
                            "section_title": sec_title,
                            "text": slide_text
                        })
                        slide_chunks = split_into_chunks(slide_text, target_tokens=380, overlap_tokens=55)
                        for c_idx, ch_txt in enumerate(slide_chunks, start=1):
                            refined_inv = refine_investigation_ids(meta["investigation_ids"], ch_txt, sec_title, source_id)
                            refined_inv_str = ", ".join(refined_inv)
                            prefix = f"[{refined_inv_str} | {source_id}: {doc_title} | {sec_title}]\n"
                            final_txt = prefix + ch_txt
                            all_chunks.append({
                                "chunk_id": f"{source_id}_p{s_idx:03d}_c{c_idx:02d}",
                                "source_id": source_id,
                                "investigation_ids": refined_inv,
                                "doc_type": meta["doc_type"],
                                "year": meta["year"],
                                "page": s_idx,
                                "section_type": "methodology",
                                "section_title": sec_title,
                                "has_table": False,
                                "has_numeric_conditions": bool(NUMERIC_COND_REGEX.search(ch_txt)),
                                "hardware": meta["hardware"],
                                "fuel_phase": meta["fuel_phase"],
                                "ocr": False,
                                "duplicate_of": None,
                                "exclude_from_default_search": False,
                                "token_estimate": estimate_tokens(final_txt),
                                "text": final_txt
                            })
                            stats["text_chunks"] += 1
            except Exception as e:
                print(f"     [!] PPTX Hatası ({fname}): {e}")
            continue

        if fname.lower().endswith(".docx"):
            try:
                d = docx.Document(fpath)
                full_text = "\n\n".join([p.text.strip() for p in d.paragraphs if p.text.strip()])
                cleaned = clean_text(full_text)
                
                # Eğer DOCX içinde "Presentations and Publications to date:" varsa ikiye ayır
                ref_split = re.split(r"Presentations and Publications to date:", cleaned, flags=re.I)
                main_part = ref_split[0].strip()
                ref_part = ref_split[1].strip() if len(ref_split) > 1 else ""

                sec_title = "Overview & Guide"
                if "procedure" in fname.lower():
                    sec_title = "Operations & Checklist"
                elif "dod" in fname.lower():
                    sec_title = "Data Description & Operations"

                all_pages_records.append({
                    "source_id": source_id,
                    "filename": fname,
                    "page": 1,
                    "section_type": "methodology",
                    "section_title": sec_title,
                    "text": main_part
                })

                raw_chunks = split_into_chunks(main_part, target_tokens=380, overlap_tokens=55)
                for idx, ch_txt in enumerate(raw_chunks, 1):
                    refined_inv = refine_investigation_ids(meta["investigation_ids"], ch_txt, sec_title, source_id)
                    refined_inv_str = ", ".join(refined_inv)
                    prefix = f"[{refined_inv_str} | {source_id}: {doc_title} | {sec_title}]\n"
                    final_txt = prefix + ch_txt
                    all_chunks.append({
                        "chunk_id": f"{source_id}_p001_c{idx:02d}",
                        "source_id": source_id,
                        "investigation_ids": refined_inv,
                        "doc_type": meta["doc_type"],
                        "year": meta["year"],
                        "page": 1,
                        "section_type": "methodology",
                        "section_title": sec_title,
                        "has_table": False,
                        "has_numeric_conditions": bool(NUMERIC_COND_REGEX.search(ch_txt)),
                        "hardware": meta["hardware"],
                        "fuel_phase": meta["fuel_phase"],
                        "ocr": False,
                        "duplicate_of": None,
                        "exclude_from_default_search": False,
                        "token_estimate": estimate_tokens(final_txt),
                        "text": final_txt
                    })
                    stats["text_chunks"] += 1

                if ref_part:
                    ref_chunks = split_into_chunks(ref_part, target_tokens=400, overlap_tokens=40)
                    for r_idx, r_txt in enumerate(ref_chunks, 1):
                        refined_inv = refine_investigation_ids(meta["investigation_ids"], r_txt, "Publications & References", source_id)
                        refined_inv_str = ", ".join(refined_inv)
                        prefix = f"[{refined_inv_str} | {source_id}: {doc_title} | Publications & References]\n"
                        final_txt = prefix + r_txt
                        all_chunks.append({
                            "chunk_id": f"{source_id}_p001_ref{r_idx:02d}",
                            "source_id": source_id,
                            "investigation_ids": refined_inv,
                            "doc_type": "bibliography",
                            "year": meta["year"],
                            "page": 1,
                            "section_type": "references",
                            "section_title": "Publications & References",
                            "has_table": False,
                            "has_numeric_conditions": False,
                            "hardware": meta["hardware"],
                            "fuel_phase": meta["fuel_phase"],
                            "ocr": False,
                            "duplicate_of": None,
                            "exclude_from_default_search": True,
                            "token_estimate": estimate_tokens(final_txt),
                            "text": final_txt
                        })
                        stats["ref_chunks_tagged"] += 1
            except Exception as e:
                print(f"     [!] DOCX Hatası ({fname}): {e}")
            continue

        # PDF İşleme (pdfplumber ile iki sütun farkındalıklı metin + tablo çıkarımı)
        try:
            fast_reader = pypdf.PdfReader(fpath) if fname == "Detailed Results FLEX.pdf" else None
            with pdfplumber.open(fpath) as pdf:
                curr_sec_type = "unknown"
                curr_sec_title = "Unknown section"

                for p_idx, page in enumerate(pdf.pages, start=1):
                    stats["total_pages"] += 1
                    forced = False

                    # ÖZEL KURAL 1: Detailed Results BAS-2.pdf (144 sayfa)
                    if fname == "Detailed Results BAS-2.pdf":
                        if p_idx <= 8:
                            continue
                        elif 111 <= p_idx <= 122:
                            curr_sec_type = "conditions"
                            curr_sec_title = "Appendix A - BASS-II Test Matrices"
                            forced = True
                        elif 137 <= p_idx <= 144:
                            curr_sec_type = "references"
                            curr_sec_title = "Appendix E - Papers and Presentations"
                            forced = True

                    # ÖZEL KURAL 2: Detailed Results FLEX.pdf (314 sayfa)
                    if fname == "Detailed Results FLEX.pdf":
                        if p_idx <= 6:
                            continue
                        elif 25 <= p_idx <= 34:
                            curr_sec_type = "conditions"
                            curr_sec_title = "Appendix A - FLEX Summary Data Tables"
                            forced = True
                        elif 35 <= p_idx <= 310:
                            curr_sec_type = "figure_caption"
                            curr_sec_title = "Appendix B - Droplet and Flame Size Plots"
                            forced = True
                        elif p_idx >= 311:
                            curr_sec_type = "references"
                            curr_sec_title = "References"
                            forced = True

                    # 1) Tabloları Bul ve Çıkar (FLEX Appendix B grafik sayfaları hariç)
                    table_bboxes = []
                    if curr_sec_type != "figure_caption":
                        try:
                            found_tables = page.find_tables()
                            for t_idx, f_tbl in enumerate(found_tables or [], start=1):
                                tbl_data = f_tbl.extract()
                                hdr_md, body_lines = format_table_markdown(tbl_data)
                                if hdr_md and body_lines and len(body_lines) >= 2:
                                    table_bboxes.append(f_tbl.bbox)
                                    batch_size = 18
                                    is_excl_tbl = (curr_sec_type == "references")
                                    for b_i in range(0, len(body_lines), batch_size):
                                        batch_rows = body_lines[b_i:b_i + batch_size]
                                        tbl_md = hdr_md + "\n" + "\n".join(batch_rows)
                                        refined_inv = refine_investigation_ids(meta["investigation_ids"], tbl_md, curr_sec_title, source_id)
                                        refined_inv_str = ", ".join(refined_inv)
                                        prefix = f"[{refined_inv_str} | {source_id}: {doc_title} | {curr_sec_title} (Table p.{p_idx})]\n"
                                        final_tbl_txt = prefix + tbl_md
                                        all_chunks.append({
                                            "chunk_id": f"{source_id}_p{p_idx:03d}_t{t_idx:02d}_{b_i//batch_size + 1}",
                                            "source_id": source_id,
                                            "investigation_ids": refined_inv,
                                            "doc_type": meta["doc_type"],
                                            "year": meta["year"],
                                            "page": p_idx,
                                            "section_type": "conditions" if not is_excl_tbl else "references",
                                            "section_title": curr_sec_title,
                                            "has_table": True,
                                            "has_numeric_conditions": True,
                                            "hardware": meta["hardware"],
                                            "fuel_phase": meta["fuel_phase"],
                                            "ocr": False,
                                            "duplicate_of": None,
                                            "exclude_from_default_search": is_excl_tbl,
                                            "token_estimate": estimate_tokens(final_tbl_txt),
                                            "text": final_tbl_txt
                                        })
                                        stats["table_chunks"] += 1
                        except Exception:
                            pass

                    # 2) Sayfa Düz Metnini Çıkar (İki sütun farkındalıklı & tablo alanı filtrelenmiş)
                    if fast_reader and curr_sec_type == "figure_caption":
                        raw_page_text = fast_reader.pages[p_idx - 1].extract_text() or ""
                    else:
                        raw_page_text = extract_page_prose_column_aware(page, table_bboxes)

                    cleaned_page = clean_text(raw_page_text)
                    if len(cleaned_page) < 40:
                        continue

                    if forced or curr_sec_type == "figure_caption":
                        segments = [(curr_sec_type, curr_sec_title, cleaned_page)]
                    else:
                        segments = split_sections(cleaned_page, curr_sec_type, curr_sec_title)
                    # Sonraki sayfa, bu sayfanın son bölümünden devam eder
                    curr_sec_type, curr_sec_title = segments[-1][0], segments[-1][1]

                    all_pages_records.append({
                        "source_id": source_id,
                        "filename": fname,
                        "page": p_idx,
                        "section_type": segments[0][0],
                        "section_title": segments[0][1],
                        "sections": [s_t for s_t, _, _ in segments],
                        "text": cleaned_page
                    })

                    c_idx = 0
                    for seg_type, seg_title, seg_text in segments:
                        is_excluded = (seg_type in ("references", "figure_caption"))
                        if seg_type == "figure_caption":
                            stats["caption_chunks_filtered"] += 1
                        elif seg_type == "references":
                            stats["ref_chunks_tagged"] += 1

                        # 3) Metni 350-450 Token (55 Token Overlap) Parçalara Böl
                        for ch_txt in split_into_chunks(seg_text, target_tokens=380, overlap_tokens=55):
                            if len(ch_txt.strip()) < 45:
                                continue
                            c_idx += 1
                            refined_inv = refine_investigation_ids(meta["investigation_ids"], ch_txt, seg_title, source_id)
                            refined_inv_str = ", ".join(refined_inv)
                            prefix = f"[{refined_inv_str} | {source_id}: {doc_title} | {seg_title}]\n"
                            final_txt = prefix + ch_txt
                            all_chunks.append({
                                "chunk_id": f"{source_id}_p{p_idx:03d}_c{c_idx:02d}",
                                "source_id": source_id,
                                "investigation_ids": refined_inv,
                                "doc_type": meta["doc_type"],
                                "year": meta["year"],
                                "page": p_idx,
                                "section_type": seg_type,
                                "section_title": seg_title,
                                "has_table": False,
                                "has_numeric_conditions": bool(NUMERIC_COND_REGEX.search(ch_txt)),
                                "hardware": meta["hardware"],
                                "fuel_phase": meta["fuel_phase"],
                                "ocr": False,
                                "duplicate_of": None,
                                "exclude_from_default_search": is_excluded,
                                "token_estimate": estimate_tokens(final_txt),
                                "text": final_txt
                            })
                            stats["text_chunks"] += 1

        except Exception as e:
            print(f"     [!] PDF Hatası ({fname}): {e}")

    # 3. PSI Metadata (.txt) Dosyalarını da K1/K2 Bağlam Parçası Olarak Ekle (manifest.csv S-030 .. S-039)
    psi_meta_map = {
        "bass_metadata.txt": ("S-036", ["BASS"], "MSG", "solid", 2013),
        "Bass-2_metadata.txt": ("S-030", ["BASS-II"], "MSG", "solid", 2022),
        "flex_metadata.txt": ("S-037", ["FLEX"], "CIR (MDCA)", "liquid", 2016),
        "saffire-1_metadata.txt": ("S-038", ["Saffire-I"], "Cygnus", "solid", 2024),
        "safire-3_metadata.txt": ("S-039", ["Saffire-III"], "Cygnus", "solid", 2024),
    }
    for mfile, (psi_id, inv_list, hw, fphase, yr) in psi_meta_map.items():
        mpath = os.path.join(RAW_PSI_DIR, mfile)
        if os.path.exists(mpath):
            with open(mpath, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            important_lines = []
            for line in lines:
                if any(line.startswith(k) for k in ["Study Identifier", "Study Title", "Comment[Approach]", "Comment[Hypothesis]", "Comment[Objective]", "Comment[Research Impacts]", "Comment[Experiment Hardware]", "Study Design Type"]):
                    important_lines.append(line.strip().replace("\t", ": "))
            summary_txt = clean_text("\n".join(important_lines))
            prefix = f"[{', '.join(inv_list)} | {psi_id}: Official PSI Metadata | Study Approach, Objective & Hardware]\n"
            final_txt = prefix + summary_txt
            all_chunks.append({
                "chunk_id": f"{psi_id}_meta_c01",
                "source_id": psi_id,
                "investigation_ids": inv_list,
                "doc_type": "overview",
                "year": yr,
                "page": 1,
                "section_type": "objective",
                "section_title": "Official PSI Metadata Summary",
                "has_table": False,
                "has_numeric_conditions": True,
                "hardware": hw,
                "fuel_phase": fphase,
                "ocr": False,
                "duplicate_of": None,
                "exclude_from_default_search": False,
                "token_estimate": estimate_tokens(final_txt),
                "text": final_txt
            })
            stats["text_chunks"] += 1

    with open(interim_pages_path, "w", encoding="utf-8") as f:
        for rec in all_pages_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    with open(chunks_output_path, "w", encoding="utf-8") as f:
        for ch in all_chunks:
            f.write(json.dumps(ch, ensure_ascii=False) + "\n")

    n_manifest = update_manifest_chunk_counts(all_chunks)
    print(f" manifest.csv chunk_count güncellendi: {n_manifest} satır değişti")

    active_chunks = [c for c in all_chunks if not c["exclude_from_default_search"]]
    print("\n" + "=" * 65)
    print(" KİŞİ A: METNE ÇEVİRME VE BÖLÜMLEME (v2 - İKİ SÜTUN & TABLO FİLTRELİ) TAMAMLANDI!")
    print("=" * 65)
    print(f" İşlenen Belge Sayısı              : {stats['total_docs']} belge + 5 PSI Metadata")
    print(f" İşlenen Toplam Sayfa              : {stats['total_pages']} sayfa")
    print(f" Üretilen Toplam Chunk (Tümü)      : {len(all_chunks)}")
    print(f" -> Aktif Arama Chunk Sayısı       : {len(active_chunks)} (Metin + Tablo)")
    print(f" -> Tablo Chunk Sayısı (has_table) : {stats['table_chunks']}")
    print(f" -> Filtrelenen FLEX Grafik Kartı  : {stats['caption_chunks_filtered']} (section_type='figure_caption')")
    print(f" -> Etiketlenen Kaynakça (Ref)     : {stats['ref_chunks_tagged']} (section_type='references')")
    print(f" Ara Çıktı (Interim)               : {interim_pages_path}")
    print(f" Nihai Çıktı (Chunks)              : {chunks_output_path}")
    print("=" * 65)

if __name__ == "__main__":
    main()
