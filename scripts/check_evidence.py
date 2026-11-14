"""Re-run the automatic check on processed/golden_table_evidence.jsonl.

Method (same rule as used when the golden table was built):
  * The source file is found from manifest.csv `repo_path`.
  * The cited location is extracted:
      PDF  "p.N"              -> pdftotext -f N -l N -layout (with pypdf fallback)
      CSV/TXT "row N"         -> line N of the file (1-based)
      XLSX "Sheet!row N"      -> that sheet row, cells joined with tabs
      DOCX "paragraph N"      -> N-th non-empty paragraph
  * Every number in the snippet must appear in the location text (with number boundaries) AND
    at least 60% of the snippet words must appear (80% if the snippet has no numbers)
    -> "found", otherwise "suspect".
  * Web sources cannot be checked automatically -> "web: check manually".

"found" only means the quoted text is at the cited place; it does not prove that the table's
interpretation or normalized value is correct.

Usage:
  python scripts/check_evidence.py            # report only
  python scripts/check_evidence.py --write    # also rewrite auto_check in the evidence file
"""
import argparse
import collections
import csv
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / "processed" / "golden_table_evidence.jsonl"
MANIFEST = ROOT / "reference" / "manifest.csv"

NUM_RE = re.compile(r"(?<![\d.])\.?\d+(?:\.\d+)?")  # keeps leading-dot decimals like ".34"
WORD_RE = re.compile(r"[A-Za-z][A-Za-z\-]{2,}")


def norm(t):
    return re.sub(r"\s+", " ", t.replace("–", "-").replace("—", "-")).lower()


def location_text(path: Path, page: str, cache={}):
    key = (str(path), page)
    if key in cache:
        return cache[key]
    suf = path.suffix.lower()
    txt = ""
    if suf == ".pdf":
        n = int(re.search(r"\d+", page).group())
        try:
            res = subprocess.run(["pdftotext", "-f", str(n), "-l", str(n), "-layout", str(path), "-"],
                                 capture_output=True, text=True)
            txt = res.stdout if res.returncode == 0 else ""
        except (FileNotFoundError, Exception):
            txt = ""
        if not txt:
            try:
                import pypdf
                reader = pypdf.PdfReader(str(path))
                if 0 < n <= len(reader.pages):
                    txt = reader.pages[n - 1].extract_text() or ""
            except Exception:
                pass
    elif suf in (".csv", ".txt"):
        n = int(re.search(r"\d+", page).group())
        for enc in ("utf-8-sig", "latin-1"):
            try:
                lines = path.read_text(encoding=enc).splitlines()
                break
            except UnicodeDecodeError:
                continue
        txt = lines[n - 1] if 0 < n <= len(lines) else ""
    elif suf == ".xlsx":
        import openpyxl
        sheet, row = page.split("!")
        n = int(re.search(r"\d+", row).group())
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True)[sheet]
        for i, r in enumerate(ws.iter_rows(values_only=True), 1):
            if i == n:
                txt = "\t".join("" if v is None else str(v) for v in r)
                break
    elif suf == ".docx":
        import docx
        n = int(re.search(r"\d+", page).group())
        paras = [p.text for p in docx.Document(str(path)).paragraphs if p.text.strip()]
        txt = paras[n - 1] if 0 < n <= len(paras) else ""
    cache[key] = txt
    return txt


def number_in(num, text):
    # number boundaries; also accept trailing zeros ("14.70" vs "14.7")
    pats = {num}
    if "." in num:
        pats.add(num.rstrip("0").rstrip("."))
    def rx(p):
        lead = r"(?<!\d)" if p.startswith(".") else r"(?<![\d.])"
        return rf"{lead}{re.escape(p)}(?![\d])"
    return any(re.search(rx(p), text) for p in pats)


def check(snippet, text):
    s, t = norm(snippet), norm(text)
    nums = NUM_RE.findall(s)
    words = WORD_RE.findall(s)
    if nums and not all(number_in(n, t) for n in nums):
        return "suspect"
    if words:
        share = sum(w in t for w in words) / len(words)
        if share < (0.6 if nums else 0.8):
            return "suspect"
    return "found"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    manifest = {r["source_id"]: r for r in csv.DictReader(open(MANIFEST, encoding="utf-8-sig"))}
    ev = [json.loads(l) for l in open(EVIDENCE, encoding="utf-8")]
    changed, counts, problems = 0, collections.Counter(), []
    for e in ev:
        if e["source_kind"] != "local":
            res = "web: check manually"
        else:
            m = manifest.get(e["source_id"])
            path = ROOT / m["repo_path"] if m and m["repo_path"] else None
            if not path or not path.exists():
                res = "suspect"
                problems.append((e, "file missing"))
            else:
                res = check(e["snippet"], location_text(path, e["page"]))
                if res == "suspect":
                    problems.append((e, "text not at cited location"))
        counts[res] += 1
        if res != e["auto_check"]:
            changed += 1
        e["auto_check"] = res
    for k, v in counts.most_common():
        print(f"{k:22} {v}")
    print(f"changed vs file: {changed}")
    for e, why in problems:
        print(f"  SUSPECT {e['investigation_id']} {e['field']} {e['source_id']} {e['page']}: {why}")
    if a.write:
        with open(EVIDENCE, "w", encoding="utf-8") as f:
            for e in ev:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
