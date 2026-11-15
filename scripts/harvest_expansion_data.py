import os
import shutil
import hashlib
import requests
import pypdf

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(BASE_DIR, "raw", "docs")
PSI_DIR = os.path.join(BASE_DIR, "raw", "psi")
os.makedirs(DOCS_DIR, exist_ok=True)
os.makedirs(PSI_DIR, exist_ok=True)

# 1. PSI Table for SAME
src_same_table = os.path.join(os.path.dirname(BASE_DIR), "..", "data", "psi_data", "SAME_Smoke_Detection_Table.csv")
src_same_table = os.path.abspath(src_same_table)
dst_same_table = os.path.join(PSI_DIR, "PSI-102_Experimental table_SAME.csv")

if os.path.exists(src_same_table):
    shutil.copyfile(src_same_table, dst_same_table)
    print(f"[OK] Copied SAME PSI table to: {dst_same_table}")
else:
    print(f"[!] Warning: {src_same_table} not found")

# 2. Documents to download
# Format: (source_id, dest_folder, local_filename, download_url)
DOWNLOADS = [
    # SAME / DAFT / DAFT-2
    ("S-044", "SAME", "SAME_20120012884.pdf", "https://ntrs.nasa.gov/api/citations/20120012884/downloads/20120012884.pdf"),
    ("S-046", "SAME", "SAME-R_20130000422.pdf", "https://ntrs.nasa.gov/api/citations/20130000422/downloads/20130000422.pdf"),
    ("S-049", "DAFT", "DAFT_20050215648.pdf", "https://ntrs.nasa.gov/api/citations/20050215648/downloads/20050215648.pdf"),
    ("S-072", "SAME", "SAME_20070031686.pdf", "https://ntrs.nasa.gov/api/citations/20070031686/downloads/20070031686.pdf"),
    
    # CFI / FLEX-2
    ("S-051", "CFI", "CFI_2017_Quad.pdf", "https://www1.grc.nasa.gov/wp-content/uploads/2017_CFI_Quad.pdf"),
    ("S-065", "CFI", "CFI_20190002838.pdf", "https://ntrs.nasa.gov/api/citations/20190002838/downloads/20190002838.pdf"),
    
    # ACME (CFI-G, BRE, E-FIELD)
    ("S-052", "ACME", "ACME_CFI-G_par_10426596.pdf", "https://par.nsf.gov/servlets/purl/10426596"),
    ("S-053", "ACME", "ACME_20210022542_JASMAC.pdf", "https://ntrs.nasa.gov/api/citations/20210022542/downloads/ACME%20JASMAC-33%2020211007.pdf"),
    ("S-056", "ACME", "ACME_20210021781_JASMAC.pdf", "https://ntrs.nasa.gov/api/citations/20210021781/downloads/JASMAC%20ACME%20paper%2020210921.pdf"),
    ("S-073", "ACME", "ACME_BRE_20160010073.pdf", "https://ntrs.nasa.gov/api/citations/20160010073/downloads/20160010073.pdf"),
    ("S-074", "ACME", "ACME_BRE_20170009141.pdf", "https://ntrs.nasa.gov/api/citations/20170009141/downloads/20170009141.pdf"),
    ("S-075", "ACME", "ACME_Overview_20210015913.pdf", "https://ntrs.nasa.gov/api/citations/20210015913/downloads/ACME_20210015913.pdf"),

    # SPICE & SLICE
    ("S-059", "SPICE", "SPICE_Dotson_2011_FSJ.pdf", "https://www.grace.umd.edu/~pbs/2011%20Dotson%20et%20al.%20FSJ.pdf"),
    ("S-060", "SPICE", "SPICE_SLICE_20140009169.pdf", "https://ntrs.nasa.gov/api/citations/20140009169/downloads/20140009169.pdf"),
    ("S-061", "SLICE", "SLICE_20140017780.pdf", "https://ntrs.nasa.gov/api/citations/20140017780/downloads/20140017780.pdf"),
    ("S-070", "SLICE", "SLICE_20150002322.pdf", "https://ntrs.nasa.gov/api/citations/20150002322/downloads/20150002322.pdf"),
    ("S-071", "SLICE", "SLICE_20160012298.pdf", "https://ntrs.nasa.gov/api/citations/20160012298/downloads/20160012298.pdf"),
    ("S-076", "SPICE", "SPICE_20090014827.pdf", "https://ntrs.nasa.gov/api/citations/20090014827/downloads/20090014827.pdf"),
]

headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SpaceAppsChallengeDataHarvester/2.0"}

results = []

for sid, subfolder, fname, url in DOWNLOADS:
    target_dir = os.path.join(DOCS_DIR, subfolder)
    os.makedirs(target_dir, exist_ok=True)
    dst_path = os.path.join(target_dir, fname)

    # Check if already exists in parent data/ntrs_pdfs
    parent_ntrs_file = os.path.join(os.path.dirname(BASE_DIR), "..", "data", "ntrs_pdfs", fname)
    if os.path.exists(parent_ntrs_file):
        shutil.copyfile(parent_ntrs_file, dst_path)
        print(f"[CACHE] Copied from local data/ntrs_pdfs: {fname}")
    elif not os.path.exists(dst_path) or os.path.getsize(dst_path) < 1000:
        print(f"[-] Downloading [{sid}] {fname} from {url}...")
        try:
            r = requests.get(url, headers=headers, stream=True, timeout=30)
            if r.status_code == 200:
                with open(dst_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=16384):
                        if chunk:
                            f.write(chunk)
                print(f"    [OK] Downloaded: {round(os.path.getsize(dst_path)/1024, 1)} KB")
            else:
                print(f"    [!] Failed with HTTP {r.status_code}")
                continue
        except Exception as e:
            print(f"    [!] Error: {e}")
            continue

    if os.path.exists(dst_path):
        size = os.path.getsize(dst_path)
        sha256 = hashlib.sha256(open(dst_path, "rb").read()).hexdigest()
        page_count = None
        try:
            reader = pypdf.PdfReader(dst_path)
            page_count = len(reader.pages)
        except Exception:
            pass

        rel_path = os.path.relpath(dst_path, BASE_DIR).replace("\\", "/")
        results.append({
            "source_id": sid,
            "filename": fname,
            "repo_path": rel_path,
            "size_bytes": size,
            "pages": page_count,
            "sha256": sha256
        })
        print(f"    -> Registered: {fname} ({page_count} pages, {size} bytes, sha={sha256[:8]}...)")

print("\n" + "="*60)
print(f"Summary: Successfully processed {len(results)}/{len(DOWNLOADS)} documents.")
print("="*60)
