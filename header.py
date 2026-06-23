import pandas as pd
from rapidfuzz import fuzz
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from collections import Counter


AMBIG = re.compile(r"^(\d{1,2})([/.\-])(\d{1,2})\2(\d{2,4})$")   # order-ambiguous numeric dates only
names = ["id", "tutor", "student", "subject", "level", "rate", "date", "status", "email", "amount", "payment", "notes", "duration",
          "attendance", "fee"]
subjects = {
    # Mathematics
    "maths": "Mathematics", "math": "Mathematics",
    "e math": "Mathematics", "emath": "Mathematics", "elementary mathematics": "Mathematics",
    "a math": "Additional Mathematics", "amath": "Additional Mathematics",
    "add math": "Additional Mathematics", "add maths": "Additional Mathematics",
    "additional maths": "Additional Mathematics",
    "f math": "Further Mathematics", "further maths": "Further Mathematics",

    # Sciences
    "bio": "Biology",
    "chem": "Chemistry",
    "phys": "Physics",
    "sci": "Science",
    "combined sci": "Combined Science", "comb science": "Combined Science",

    # Humanities
    "geog": "Geography", "geo": "Geography",
    "hist": "History",
    "econs": "Economics", "econ": "Economics", "eco": "Economics",
    "ss": "Social Studies", "soc studies": "Social Studies",
    "lit": "Literature", "english literature": "Literature", "literature in english": "Literature",
    "combined humanities": "Combined Humanities", "comb humanities": "Combined Humanities",

    # Languages
    "eng": "English", "english language": "English",
    "gp": "General Paper", "general paper": "General Paper",
    "cl": "Chinese", "chinese language": "Chinese",
    "higher chinese": "Chinese", "hcl": "Chinese",       # see Mother Tongue note above
    "ml": "Malay", "malay language": "Malay", "higher malay": "Malay",
    "tl": "Tamil", "tamil language": "Tamil", "higher tamil": "Tamil",

    # Applied / others
    "poa": "Principles of Accounts", "accounts": "Principles of Accounts",
    "cs": "Computing", "comp sci": "Computing", "computer science": "Computing",
    "d&t": "Design and Technology", "dt": "Design and Technology",
    "f&n": "Food and Nutrition", "fn": "Food and Nutrition",
    "home econ": "Food and Nutrition", "home economics": "Food and Nutrition",
    "ki": "Knowledge and Inquiry",
    "pw": "Project Work",
    "ess": "Exercise and Sports Science",
}
#============================= File loading ===========================
def load(filepath):
    loaded_df = pd.read_excel(filepath, header=None, dtype=str)
    return loaded_df
#============================= Header Detection ===========================
# === vocab matching ===
def matches(cell, names, cutoff=88):                 # any fuzzy match in names cutoff @88 prevents late from matching
    cell = str(cell).strip().lower()
    return any(fuzz.partial_ratio(n.lower(), cell) >= cutoff for n in names)

def find_header_row(df, names, min_matches=2):        # header row = enough names on one row
    for i in range(len(df)):
        row = [str(c).strip() for c in df.iloc[i]]
        hits = sum(1 for c in row if c and matches(c, names))
        if hits >= min_matches:
            return i

# === block detection ===
def cell_kind(v):                                     # coarse type, for block detection
    s = str(v).strip()
    if not s or s.lower() == "nan":
        return "empty"
    try:
        float(s.replace(",", "").lstrip("$")); return "num"
    except ValueError:
        return "text"

def same(a, b):                                       # empty cells act as wildcards
    return all(x == y or "empty" in (x, y) for x, y in zip(a, b))

# === headerless column labelling (categorical, then stem) ===
def is_categorical(series, max_unique=10, ratio=0.5):
    vals = [str(v).strip().lower() for v in series
            if str(v).strip() and str(v).strip().lower() != "nan"]
    if not vals:
        return False
    uniques = set(vals)
    return len(uniques) <= max_unique and len(uniques) / len(vals) <= ratio

def common_prefix(strs):
    out = ""
    for chars in zip(*strs):
        if len(set(chars)) == 1:
            out += chars[0]
        else:
            break
    return out

def varying_token(mids):
    parts = [m for m in mids if m]
    if not parts:
        return ""
    if all(m.isdigit() for m in parts):
        ch = "#"
    elif all(m.isalpha() for m in parts):
        ch = "A"
    else:
        ch = "X"
    return ch * len(parts[0]) if len({len(m) for m in parts}) == 1 else ch

def recommend_header(series):
    vals = [str(v).strip() for v in series
            if str(v).strip() and str(v).strip().lower() != "nan"]
    if len(vals) < 2:
        return None
    pre = common_prefix(vals)
    suf = common_prefix([v[::-1] for v in vals])[::-1]
    shortest = min(len(v) for v in vals)
    if len(pre) + len(suf) > shortest:
        suf = suf[len(pre) + len(suf) - shortest:]
    mids = [v[len(pre): len(v) - len(suf)] for v in vals]
    if all(m == "" for m in mids):
        return pre or None
    if not pre and not suf:
        return None
    return f"{pre}{varying_token(mids)}{suf}"

def label_column(series):                             # categorical first, then stem
    if is_categorical(series):
        seen = []
        for v in series:
            s = str(v).strip()
            if s and s.lower() != "nan" and s not in seen:
                seen.append(s)
        return "categorical: " + ",".join(seen)
    return recommend_header(series)


# === main ===
def find_header(df):

    header_row = find_header_row(df, names)
    if header_row is None:
        sigs = [[cell_kind(c) for c in df.iloc[i]] for i in range(len(df))]
        block_start = next((i for i in range(len(df) - 1) if same(sigs[i], sigs[i+1])), None)
        if block_start is None or block_start == 0:
            # no header row -> return the generated names
            return [label_column(df[c]) or f"col_{i}"
                    for i, c in enumerate(df.columns)]
        else:
            # header row exists, directly above the block -> return its row number
            return block_start - 1
    else:
        # vocab matched a header row -> return its row number
        return header_row