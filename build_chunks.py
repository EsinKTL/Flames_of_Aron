import os
import re
import json
import unicodedata
import pdfplumber
import pypdf
import docx

BASE_DIR = r"C:\Users\ihsan\Desktop\NASA\Flames_of_Aron-main\Flames_of_Aron"
RAW_DOCS_DIR = os.path.join(BASE_DIR, "raw", "docs")
RAW_PSI_DIR = os.path.join(BASE_DIR, "raw", "psi")
INTERIM_DIR = os.path.join(BASE_DIR, "interim")
PROCESSED_DIR = os.path.join(BASE_DIR, "processed")
LOGS_DIR = os.path.join(BASE_DIR, "logs")
EVAL_DIR = os.path.join(BASE_DIR, "eval")

for d in [INTERIM_DIR, PROCESSED_DIR, LOGS_DIR, EVAL_DIR]:
    os.makedirs(d, exist_ok=True)

# Belge Kayıt ve Metadata Haritası (Taslak Rapor Bölüm 6.1 Şeması - Tam İngilizce Alan Değerleri)
DOC_REGISTRY = {
    "Detailed Results BAS-2.pdf": {
        "source_id": "S-013",
        "doc_title": "NASA/TM-20210011385 BASS-II Summary Report",
        "investigation_ids": ["BASS-II", "BASS"],
        "doc_type": "results",
        "year": 2021,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20160000593.pdf": {
        "source_id": "S-013b",
        "doc_title": "Combustion of Solids in Microgravity: Results from BASS-II",
        "investigation_ids": ["BASS-II"],
        "doc_type": "results",
        "year": 2016,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20205004657.pdf": {
        "source_id": "S-013c",
        "doc_title": "Effects of Confinement on Flame Spread in Microgravity",
        "investigation_ids": ["BASS-II"],
        "doc_type": "results",
        "year": 2020,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20140011099.pdf": {
        "source_id": "S-010",
        "doc_title": "Thickness and Fuel Preheating Effects on Material Flammability (BASS)",
        "investigation_ids": ["BASS"],
        "doc_type": "results",
        "year": 2014,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20150008961.pdf": {
        "source_id": "S-010b",
        "doc_title": "Microgravity Flammability of PMMA Rods in Concurrent Flow",
        "investigation_ids": ["BASS", "BASS-II"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_20150008962.pdf": {
        "source_id": "S-010c",
        "doc_title": "Concurrent Flame Growth, Spread and Extinction over Composite Fabric (BASS)",
        "investigation_ids": ["BASS", "BASS-II"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS_SRD.pdf": {
        "source_id": "S-011",
        "doc_title": "Science Requirements Document (SRD) for BASS",
        "investigation_ids": ["BASS"],
        "doc_type": "design",
        "year": 2010,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-II_SRD.pdf": {
        "source_id": "S-014",
        "doc_title": "Science Requirements Document (SRD) for BASS-II",
        "investigation_ids": ["BASS-II"],
        "doc_type": "design",
        "year": 2013,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-II data FAQ.docx": {
        "source_id": "S-015",
        "doc_title": "BASS-II Data FAQ and PI Test Matrix Guide",
        "investigation_ids": ["BASS-II", "BASS"],
        "doc_type": "overview",
        "year": 2017,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "BASS-II Procedure.docx": {
        "source_id": "S-016",
        "doc_title": "BASS-II Astronaut Operations Procedure & Checklist",
        "investigation_ids": ["BASS-II"],
        "doc_type": "methodology",
        "year": 2014,
        "hardware": "MSG",
        "fuel_phase": "solid"
    },
    "Detailed Results FLEX.pdf": {
        "source_id": "S-028",
        "doc_title": "NASA/TP-2015-216046 Detailed Results from FLEX",
        "investigation_ids": ["FLEX"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "FLEX_20090014812.pdf": {
        "source_id": "S-029",
        "doc_title": "Multi-User Droplet Combustion Apparatus - FLEX Hardware",
        "investigation_ids": ["FLEX", "FLEX-2"],
        "doc_type": "design",
        "year": 2009,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "FLEX_20130014061.pdf": {
        "source_id": "S-028b",
        "doc_title": "Methanol Droplet Combustion in Oxygen-Inert Environments (FLEX)",
        "investigation_ids": ["FLEX"],
        "doc_type": "results",
        "year": 2013,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "20150018397.pdf": {
        "source_id": "S-034",
        "doc_title": "Combustion Characteristics in Cool-Flame Regime of n-Heptane (CFI / FLEX)",
        "investigation_ids": ["CFI", "FLEX", "FLEX-2"],
        "doc_type": "results",
        "year": 2015,
        "hardware": "CIR (MDCA)",
        "fuel_phase": "liquid"
    },
    "Saffire_20180005168.pdf": {
        "source_id": "S-001",
        "doc_title": "Saffire: A Novel Approach to Study of Spacecraft Fire Safety (Saffire I-III Results)",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "results",
        "year": 2018,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20170000230.pdf": {
        "source_id": "S-003",
        "doc_title": "Operation and Development Status of the Spacecraft Fire Experiments (Saffire)",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "overview",
        "year": 2017,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20170001636.pdf": {
        "source_id": "S-002",
        "doc_title": "The Spacecraft Fire Experiment (Saffire) - Objectives, Development and Status",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "design",
        "year": 2017,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "SAFFIRE_Offgassing_Testing_Strategy.pdf": {
        "source_id": "S-002b",
        "doc_title": "SAFFIRE Offgassing Testing Strategy",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "design",
        "year": 2016,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "SFSDP-VIS-0295_Saffire 1 and 3_Thermocouple Placement.pdf": {
        "source_id": "S-008",
        "doc_title": "Saffire-I and Saffire-III Thermocouple Placement and Sensor Layout",
        "investigation_ids": ["Saffire-I", "Saffire-III"],
        "doc_type": "design",
        "year": 2016,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "SAFFIRE-I and SAFFIRE-III DoD.docx": {
        "source_id": "S-007",
        "doc_title": "Saffire-I and Saffire-III Description of Data (DoD) & Operations",
        "investigation_ids": ["Saffire-I", "Saffire-III"],
        "doc_type": "design",
        "year": 2017,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "Saffire_20220002714.pdf": {
        "source_id": "S-004",
        "doc_title": "Model Development of Large-Scale Spacecraft Fires During Saffire Experiments",
        "investigation_ids": ["Saffire-I", "Saffire-II", "Saffire-III"],
        "doc_type": "results",
        "year": 2022,
        "hardware": "Cygnus",
        "fuel_phase": "solid"
    },
    "np-2015-10-034-jsc_combustion_in_reduced_gravity-iss-mini-book-011116-508.pdf": {
        "source_id": "S-012",
        "doc_title": "NASA ISS Research Mini-Book: Combustion in Reduced Gravity",
        "investigation_ids": ["BASS", "BASS-II", "FLEX", "FLEX-2", "SLICE", "SPICE", "SAME", "Saffire-I"],
        "doc_type": "overview",
        "year": 2016,
        "hardware": "MSG / CIR",
        "fuel_phase": "multi-phase"
    },
    "20030002834.pdf": {
        "source_id": "S-052a",
        "doc_title": "Microgravity Combustion Science and Spacecraft Fire Safety Overview",
        "investigation_ids": ["BASS", "FLEX", "SAME"],
        "doc_type": "overview",
        "year": 2003,
        "hardware": "MSG / CIR",
        "fuel_phase": "multi-phase"
    },
    "nasa.pdf": {
        "source_id": "S-052b",
        "doc_title": "NASA Microgravity Combustion Program Overview",
        "investigation_ids": ["BASS", "FLEX", "ACME-CFI-G"],
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
        for p in PROTECTED_HYPHENS:
            if full.lower() == p.lower():
                return p
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
            if f.lower().endswith((".pdf", ".docx")):
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
                    prefix = f"[{inv_str} | {source_id}: {doc_title} | {sec_title}]\n"
                    final_txt = prefix + ch_txt
                    all_chunks.append({
                        "chunk_id": f"{source_id}_p001_c{idx:02d}",
                        "source_id": source_id,
                        "investigation_ids": meta["investigation_ids"],
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
                        prefix = f"[{inv_str} | {source_id}: {doc_title} | Publications & References]\n"
                        final_txt = prefix + r_txt
                        all_chunks.append({
                            "chunk_id": f"{source_id}_p001_ref{r_idx:02d}",
                            "source_id": source_id,
                            "investigation_ids": meta["investigation_ids"],
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
                curr_sec_type = "objective"
                curr_sec_title = "Introduction & Overview"

                for p_idx, page in enumerate(pdf.pages, start=1):
                    stats["total_pages"] += 1

                    # ÖZEL KURAL 1: Detailed Results BAS-2.pdf (144 sayfa)
                    if fname == "Detailed Results BAS-2.pdf":
                        if p_idx <= 8:
                            continue
                        elif 111 <= p_idx <= 122:
                            curr_sec_type = "conditions"
                            curr_sec_title = "Appendix A - BASS-II Test Matrices"
                        elif 137 <= p_idx <= 144:
                            curr_sec_type = "references"
                            curr_sec_title = "Appendix E - Papers and Presentations"

                    # ÖZEL KURAL 2: Detailed Results FLEX.pdf (314 sayfa)
                    if fname == "Detailed Results FLEX.pdf":
                        if p_idx <= 6:
                            continue
                        elif 25 <= p_idx <= 34:
                            curr_sec_type = "conditions"
                            curr_sec_title = "Appendix A - FLEX Summary Data Tables"
                        elif 35 <= p_idx <= 310:
                            curr_sec_type = "figure_caption"
                            curr_sec_title = "Appendix B - Droplet and Flame Size Plots"
                        elif p_idx >= 311:
                            curr_sec_type = "references"
                            curr_sec_title = "References"

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
                                        prefix = f"[{inv_str} | {source_id}: {doc_title} | {curr_sec_title} (Table p.{p_idx})]\n"
                                        final_tbl_txt = prefix + tbl_md
                                        all_chunks.append({
                                            "chunk_id": f"{source_id}_p{p_idx:03d}_t{t_idx:02d}_{b_i//batch_size + 1}",
                                            "source_id": source_id,
                                            "investigation_ids": meta["investigation_ids"],
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

                    if curr_sec_type not in ("figure_caption",):
                        curr_sec_type, curr_sec_title = detect_section(cleaned_page, curr_sec_type, curr_sec_title)

                    all_pages_records.append({
                        "source_id": source_id,
                        "filename": fname,
                        "page": p_idx,
                        "section_type": curr_sec_type,
                        "section_title": curr_sec_title,
                        "text": cleaned_page
                    })

                    is_excluded = (curr_sec_type in ("references", "figure_caption"))
                    if curr_sec_type == "figure_caption":
                        stats["caption_chunks_filtered"] += 1
                    elif curr_sec_type == "references":
                        stats["ref_chunks_tagged"] += 1

                    # 3) Metni 350-450 Token (55 Token Overlap) Parçalara Böl
                    page_chunks = split_into_chunks(cleaned_page, target_tokens=380, overlap_tokens=55)
                    for c_idx, ch_txt in enumerate(page_chunks, start=1):
                        if len(ch_txt.strip()) < 45:
                            continue
                        prefix = f"[{inv_str} | {source_id}: {doc_title} | {curr_sec_title}]\n"
                        final_txt = prefix + ch_txt
                        all_chunks.append({
                            "chunk_id": f"{source_id}_p{p_idx:03d}_c{c_idx:02d}",
                            "source_id": source_id,
                            "investigation_ids": meta["investigation_ids"],
                            "doc_type": meta["doc_type"],
                            "year": meta["year"],
                            "page": p_idx,
                            "section_type": curr_sec_type,
                            "section_title": curr_sec_title,
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

    # 3. PSI Metadata (.txt) Dosyalarını da K1/K2 Bağlam Parçası Olarak Ekle
    psi_meta_map = {
        "bass_metadata.txt": ("PSI-26", ["BASS"], "MSG", "solid", 2013),
        "Bass-2_metadata.txt": ("PSI-25", ["BASS-II"], "MSG", "solid", 2022),
        "flex_metadata.txt": ("PSI-69", ["FLEX"], "CIR (MDCA)", "liquid", 2016),
        "saffire-1_metadata.txt": ("PSI-98", ["Saffire-I"], "Cygnus", "solid", 2024),
        "safire-3_metadata.txt": ("PSI-100", ["Saffire-III"], "Cygnus", "solid", 2024),
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
