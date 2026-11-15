import csv
import hashlib
import os
import pypdf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST_PATH = os.path.join(BASE_DIR, "reference", "manifest.csv")

def get_file_info(rel_path):
    full_path = os.path.join(BASE_DIR, rel_path)
    if not os.path.exists(full_path):
        return None
    sz = os.path.getsize(full_path)
    sha = hashlib.sha256(open(full_path, "rb").read()).hexdigest()
    pages = ""
    if full_path.lower().endswith(".pdf"):
        try:
            pages = str(len(pypdf.PdfReader(full_path).pages))
        except Exception:
            pass
    elif full_path.lower().endswith(".csv"):
        try:
            with open(full_path, "r", encoding="utf-8", errors="ignore") as f:
                pages = str(len(f.readlines()))
        except Exception:
            pass
    return sz, sha, pages

FILE_MAP = {
    "S-044": "raw/docs/SAME/SAME_20120012884.pdf",
    "S-046": "raw/docs/SAME/SAME-R_20130000422.pdf",
    "S-049": "raw/docs/DAFT/DAFT_20050215648.pdf",
    "S-051": "raw/docs/CFI/CFI_2017_Quad.pdf",
    "S-052": "raw/docs/ACME/ACME_CFI-G_par_10426596.pdf",
    "S-053": "raw/docs/ACME/ACME_20210022542_JASMAC.pdf",
    "S-056": "raw/docs/ACME/ACME_20210021781_JASMAC.pdf",
    "S-059": "raw/docs/SPICE/SPICE_Dotson_2011_FSJ.pdf",
    "S-060": "raw/docs/SPICE/SPICE_SLICE_20140009169.pdf",
    "S-061": "raw/docs/SLICE/SLICE_20140017780.pdf",
    "S-065": "raw/docs/CFI/CFI_20190002838.pdf",
    "S-070": "raw/docs/SLICE/SLICE_20150002322.pdf",
    "S-071": "raw/docs/SLICE/SLICE_20160012298.pdf",
}

with open(MANIFEST_PATH, "r", encoding="utf-8-sig", newline="") as f:
    reader = csv.DictReader(f)
    fieldnames = reader.fieldnames
    rows = list(reader)

for r in rows:
    sid = r["source_id"]
    if sid in FILE_MAP:
        rel_path = FILE_MAP[sid]
        info = get_file_info(rel_path)
        if info:
            sz, sha, pages = info
            r["repo_path"] = rel_path
            r["size_bytes"] = str(sz)
            r["sha256"] = sha
            r["pages"] = pages
            r["downloaded"] = "yes"
            r["status"] = "downloaded"
            r["access_date"] = "2026-11-15"

# Now add new documents S-072, S-073, S-074, S-076, S-077 if not present
existing_sids = {r["source_id"] for r in rows}

NEW_RECORDS = [
    {
        "source_id": "S-072",
        "investigation": "SAME;DAFT",
        "psi_id": "",
        "role": "results",
        "title": "Particle and Smoke Detection on ISS for Next Generation Smoke Detectors",
        "authors": "Urban D.L. et al.",
        "year": "2007",
        "file_type": "pdf",
        "source_platform": "NTRS",
        "ntrs_id": "20070031686",
        "doi": "",
        "url": "https://ntrs.nasa.gov/citations/20070031686",
        "psi_file_name": "",
        "repo_path": "raw/docs/SAME/SAME_20070031686.pdf",
        "license_attribution": "NASA work, US public domain; attribution required",
        "status": "downloaded",
        "notes": "Covers both SAME smoke particle sizing and DAFT testing"
    },
    {
        "source_id": "S-073",
        "investigation": "ACME-BRE",
        "psi_id": "",
        "role": "results",
        "title": "A Burning Rate Emulator (BRE) for Study in Microgravity",
        "authors": "Dehghani P., Quintiere J., Sunderland P.B.",
        "year": "2016",
        "file_type": "pdf",
        "source_platform": "NTRS",
        "ntrs_id": "20160010073",
        "doi": "",
        "url": "https://ntrs.nasa.gov/citations/20160010073",
        "psi_file_name": "",
        "repo_path": "raw/docs/ACME/ACME_BRE_20160010073.pdf",
        "license_attribution": "NASA work, US public domain; attribution required",
        "status": "downloaded",
        "notes": "Detailed BRE experiment design and heat flux measurements"
    },
    {
        "source_id": "S-074",
        "investigation": "ACME-BRE",
        "psi_id": "",
        "role": "results",
        "title": "Emulation of Condensed Fuel Flames Using a Burning Rate Emulator (BRE) in Microgravity",
        "authors": "Quintiere J. et al.",
        "year": "2017",
        "file_type": "pdf",
        "source_platform": "NTRS",
        "ntrs_id": "20170009141",
        "doi": "",
        "url": "https://ntrs.nasa.gov/citations/20170009141",
        "psi_file_name": "",
        "repo_path": "raw/docs/ACME/ACME_BRE_20170009141.pdf",
        "license_attribution": "NASA work, US public domain; attribution required",
        "status": "downloaded",
        "notes": "Combustion Institute paper on BRE microgravity flame emulation"
    },
    {
        "source_id": "S-076",
        "investigation": "SPICE",
        "psi_id": "",
        "role": "overview",
        "title": "Smoke Point in Co-flow Experiment (SPICE)",
        "authors": "Urban D.L. et al.",
        "year": "2009",
        "file_type": "pdf",
        "source_platform": "NTRS",
        "ntrs_id": "20090014827",
        "doi": "",
        "url": "https://ntrs.nasa.gov/citations/20090014827",
        "psi_file_name": "",
        "repo_path": "raw/docs/SPICE/SPICE_20090014827.pdf",
        "license_attribution": "NASA work, US public domain; attribution required",
        "status": "downloaded",
        "notes": "4-page experiment summary for SPICE co-flow duct in MSG"
    },
    {
        "source_id": "S-077",
        "investigation": "SAME",
        "psi_id": "PSI-102",
        "role": "data table",
        "title": "SAME ISS Smoke Detection Flight Table",
        "authors": "Urban D.L. et al.",
        "year": "2007",
        "file_type": "csv",
        "source_platform": "PSI",
        "ntrs_id": "",
        "doi": "10.60555/psi-102",
        "url": "https://psi.nasa.gov/physci/repo/data/investigations/PSI-102",
        "psi_file_name": "PSI-102_Experimental table_SAME.csv",
        "repo_path": "raw/psi/PSI-102_Experimental table_SAME.csv",
        "license_attribution": "CC0-1.0; cite PSI",
        "status": "downloaded",
        "notes": "ISS Expedition 15 smoke aerosol measurements: airflow, weight loss rate, aging duration"
    }
]

for rec in NEW_RECORDS:
    if rec["source_id"] not in existing_sids:
        info = get_file_info(rec["repo_path"])
        if info:
            rec["size_bytes"] = str(info[0])
            rec["sha256"] = info[1]
            rec["pages"] = info[2]
            rec["downloaded"] = "yes"
            rec["access_date"] = "2026-11-15"
        full_rec = {fn: rec.get(fn, "") for fn in fieldnames}
        rows.append(full_rec)

# Write back preserving BOM and CRLF
with open(MANIFEST_PATH, "w", encoding="utf-8-sig", newline="\r\n") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)

print(f"Manifest successfully updated. Total rows: {len(rows)}")
