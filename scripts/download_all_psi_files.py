import os
import requests
import zipfile
import io
import json

RAW_PSI = os.path.abspath("raw/psi")
os.makedirs(RAW_PSI, exist_ok=True)
headers = {'User-Agent': 'Mozilla/5.0'}

def download_file(study_id, remote_name, local_name):
    dest = os.path.join(RAW_PSI, local_name)
    if os.path.exists(dest):
        print(f"[EXISTS] {local_name}")
        return dest
    url = f"https://psi.nasa.gov/geode-py/ws/studies/{study_id}/download?file={remote_name}"
    print(f"Downloading {remote_name} from {study_id}...")
    try:
        r = requests.get(url, headers=headers, allow_redirects=True, timeout=60)
        if r.status_code == 200:
            with open(dest, 'wb') as f:
                f.write(r.content)
            print(f"  -> Saved {local_name} ({len(r.content)} bytes)")
            return dest
        else:
            print(f"  -> Failed: HTTP {r.status_code}")
    except Exception as e:
        print(f"  -> Error: {e}")
    return None

def extract_metadata_zip(study_id, zip_name, output_txt_name):
    dest = os.path.join(RAW_PSI, output_txt_name)
    if os.path.exists(dest):
        print(f"[EXISTS] {output_txt_name}")
        return dest
    url = f"https://psi.nasa.gov/geode-py/ws/studies/{study_id}/download?file={zip_name}"
    print(f"Extracting metadata from {zip_name} ({study_id})...")
    try:
        r = requests.get(url, headers=headers, allow_redirects=True, timeout=30)
        if r.status_code == 200:
            zf = zipfile.ZipFile(io.BytesIO(r.content))
            for member in zf.namelist():
                if "investigation" in member.lower() or member.endswith(".txt"):
                    content = zf.read(member).decode('utf-8', errors='ignore')
                    with open(dest, 'w', encoding='utf-8') as f:
                        f.write(content)
                    print(f"  -> Extracted {member} to {output_txt_name} ({len(content)} chars)")
                    return dest
        else:
            print(f"  -> Failed: HTTP {r.status_code}")
    except Exception as e:
        print(f"  -> Error: {e}")
    return None

def generate_metadata_from_es(acc, output_txt_name):
    dest = os.path.join(RAW_PSI, output_txt_name)
    if os.path.exists(dest):
        print(f"[EXISTS] {output_txt_name}")
        return dest
    print(f"Generating metadata for {acc} from PSI repo...")
    r = requests.get(f"https://psi.nasa.gov/geode-py/ws/repo/search?query=*&size=200", headers=headers)
    if r.status_code != 200:
        return None
    for h in r.json().get('hits', {}).get('hits', []):
        s = h['_source']
        if s.get('Accession') == acc:
            p = s.get('Person', {})
            author = f"{p.get('First Name', '')} {p.get('Last Name', '')}".strip()
            hw = s.get('Experiment Hardware', {})
            hw_name = hw.get('Name', '') if isinstance(hw, dict) else str(hw)
            hw_link = hw.get('Link', '') if isinstance(hw, dict) else ''
            
            lines = [
                "INVESTIGATION",
                f"Investigation Identifier\t{acc}",
                f"Investigation Title\t{s.get('Title', '')}",
                f"Investigation Description\t{s.get('Objectives', '')}",
                f"Investigation Submission Date\t{s.get('Investigation Start Date', '')}",
                f"Investigation Public Release Date\t{s.get('Investigation End Date', '')}",
                "INVESTIGATION CONTACTS",
                f"Investigation Person\t{author}",
                f"Investigation Affiliation\t{s.get('Monitoring Center', '')}",
                "STUDY",
                f"Study Identifier\t{acc}",
                f"Study Title\t{s.get('Title', '')}",
                f"Comment[Acronym]\t{s.get('Acronym', '')}",
                f"Comment[Approach]\t{s.get('Approach', '')}",
                f"Comment[Hypothesis]\t{s.get('Hypothesis', '')}",
                f"Comment[Objectives]\t{s.get('Objectives', '')}",
                f"Comment[Flight Platform]\t{s.get('Flight Platform', '')}",
                f"Comment[Experiment Hardware]\t{hw_name}",
                f"Comment[Experiment Hardware Link]\t{hw_link}",
                f"Comment[Research Area]\t{s.get('Research Area', '')} - {s.get('SubResearch Area', '')}",
                f"Comment[Keywords]\t{s.get('Keywords', '')}",
                f"Comment[Research Impacts/Earth Benefits]\t{s.get('Research Impacts/Earth Benefits', '')}",
                f"Comment[Publication Author List]\t{s.get('Publication Author List', '')}",
                f"Comment[Publication Title]\t{s.get('Publication Title', '')}",
            ]
            content = "\n".join(lines) + "\n"
            with open(dest, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"  -> Generated {output_txt_name} ({len(content)} chars)")
            return dest
    return None

print("=== 1. Metadata Files ===")
extract_metadata_zip("PSI-102", "PSI-102_metadata_PSI-170_SAME.zip", "same_metadata.txt")
extract_metadata_zip("PSI-47", "PSI-47_metadata_PSI-126_DAFT_DAFT-2.zip", "daft_metadata.txt")
extract_metadata_zip("PSI-39", "PSI-39_metadata_PSI-118_CFI.zip", "cfi_metadata.txt")
extract_metadata_zip("PSI-159", "PSI-159_metadata_PSI-159-ISA.zip", "acme_cfi_g_metadata.txt")
extract_metadata_zip("PSI-60", "PSI-60_metadata_NEWID-5_Computational and Ex.zip", "spice_metadata.txt")

generate_metadata_from_es("PSI-101", "same_r_metadata.txt")
generate_metadata_from_es("PSI-20", "acme_bre_metadata.txt")
generate_metadata_from_es("PSI-22", "acme_efield_metadata.txt")
generate_metadata_from_es("PSI-106", "slice_metadata.txt")

print("\n=== 2. Experimental Data Tables ===")
download_file("PSI-106", "PSI-106_Experimental table_Slice.csv", "PSI-106_Experimental table_Slice.csv")
download_file("PSI-20", "PSI-20_Experimental table_ACME BRE.csv", "PSI-20_Experimental table_ACME BRE.csv")
download_file("PSI-159", "PSI-159_Experimental table_CFI-G_Normal Flames.csv", "PSI-159_Experimental table_CFI-G_Normal Flames.csv")
download_file("PSI-159", "PSI-159_Experimental table_CFI-G_Inverse Flames.csv", "PSI-159_Experimental table_CFI-G_Inverse Flames.csv")
download_file("PSI-101", "PSI-101_Analyzed Data_SAME, SAME-R_Results.xlsx", "PSI-101_Analyzed Data_SAME_SAME-R_Results.xlsx")
download_file("PSI-101", "PSI-101_Engineering Documents_SAME VPRED Matrix PLN-005 Baseline.xls", "PSI-101_SAME_VPRED_Matrix.xls")
download_file("PSI-47", "PSI-47_Analyzed Data_DAFT Retrieved Data Summary.xls", "PSI-47_Analyzed Data_DAFT Retrieved Data Summary.xls")
download_file("PSI-39", "PSI-39_Science Documents_CFI_DataSummary_Spreadsheet_Jan2021.xlsx", "PSI-39_CFI_DataSummary_Spreadsheet.xlsx")
download_file("PSI-107", "PSI-107_Raw Data_Spice_Flight_Flamelength.xls", "PSI-107_Raw Data_Spice_Flight_Flamelength.xls")
download_file("PSI-107", "PSI-107_Raw Data_SmokePointReview-0g-3.xlsx", "PSI-107_SmokePointReview.xlsx")

print("\nAll downloads finished successfully!")
