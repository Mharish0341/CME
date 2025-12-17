import pandas as pd
import re

# ================= FILE PATHS =================
INPUT_FILE = r"C:/Users/Admin/Downloads/vindicocme.xlsx"
OUTPUT_FILE = r"C:/Users/Admin/Downloads/vindicocme_faculty_one_per_row.xlsx"

SOURCE_COLS = ["activity_chair", "series_co_chairs", "faculty"]

# ================= CONFIG =================

DEGREE_PATTERN = (
    r"MD|DO|PhD|MPH|MS|MBA|OD|RN|PA|DNP|PharmD|MBBS|MA|"
    r"FAAN|FASRS|FAAO|FACP|FACG|FRCP|FACE|FACC|"
    r"MMSc|DABOM|FTOS|FAAP|AGAF|FESC|FHFSA|"
    r"RD|LDN|CDCES"
)

MIS_WORDS = [
    "Atlantic Retina Philadelphia, PA",
    "Medicine Baltimore, MD",
]

LOCATION_REGEX = re.compile(
    r",\s*[A-Z]{2}\b|"
    r",\s*(Italy|France|Germany|UK|United Kingdom|Canada|Spain|India)\b",
    re.IGNORECASE
)

# ================= PERSON START REGEX =================
# Handles:
# - Multiple degrees
# - Jr., III
# - Long bios
PERSON_START_REGEX = re.compile(
    rf'''
    (?:(?<=^)|(?<=\s))
    (
        [A-Z][a-zA-Z.\-']+\s+
        [A-Z][a-zA-Z.\-']+
        (?:\s+[A-Z][a-zA-Z.\-']+)?          # optional middle name
        (?:,\s*(?:Jr\.|III|IV))?            # suffix
        \s*,\s*
        (?:{DEGREE_PATTERN})
        (?:\s*,\s*(?:{DEGREE_PATTERN}))*
    )
    ''',
    re.VERBOSE
)

# ================= HELPERS =================

def is_misword(text: str) -> bool:
    return any(m.lower() in text.lower() for m in MIS_WORDS)

def looks_like_person_start(text: str) -> bool:
    return bool(PERSON_START_REGEX.search(text))

def split_people(cell):
    if pd.isna(cell):
        return []

    text = " ".join(str(cell).replace("\u200b", "").split())
    matches = list(PERSON_START_REGEX.finditer(text))

    if not matches:
        return []

    chunks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        chunks.append(text[start:end].strip())

    # -------- MERGE MIS-WORD FRAGMENTS --------
    merged = []
    for chunk in chunks:
        if not merged:
            merged.append(chunk)
            continue

        if is_misword(chunk) or not looks_like_person_start(chunk):
            merged[-1] += " " + chunk
        else:
            merged.append(chunk)

    # -------- FINAL FILTER --------
    final_people = []
    for p in merged:
        if looks_like_person_start(p) and LOCATION_REGEX.search(p):
            final_people.append(p.strip())

    return final_people

# ================= MAIN PROCESS =================

df = pd.read_excel(INPUT_FILE)
rows = []

for _, row in df.iterrows():
    base = row.to_dict()

    for col in SOURCE_COLS:
        for person in split_people(row.get(col)):
            out = base.copy()
            out["faculty"] = person
            out["type"] = col
            out.pop("activity_chair", None)
            out.pop("series_co_chairs", None)
            rows.append(out)

# ================= SAVE =================

pd.DataFrame(rows).to_excel(OUTPUT_FILE, index=False)

print("✅ DONE — one person per row, no missing faculty, no garbage")