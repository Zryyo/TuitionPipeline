import pandas as pd
from rapidfuzz import fuzz
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from collections import Counter
from header import is_categorical

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
# ============================ dates ============================


def detect_sep_convention(values):
    """Per separator: day-first(True)/month-first(False)/undecidable(None),
    using only the unambiguous values (a slot > 12)."""
    votes = {}
    for v in values:
        m = AMBIG.match(str(v).strip())
        if not m:
            continue
        a, sep, b = int(m.group(1)), m.group(2), int(m.group(3))
        if a > 12:
            votes.setdefault(sep, set()).add("day")
        elif b > 12:
            votes.setdefault(sep, set()).add("month")
    return {sep: (True if s == {"day"} else False if s == {"month"} else None)
            for sep, s in votes.items()}

def parse_column_dates(series, default_dayfirst=None):
    values = [str(v).strip() for v in series
              if str(v).strip() and str(v).strip().lower() != "nan"]
    conv = detect_sep_convention(values)
    return [_parse_one(v, conv, default_dayfirst) for v in series]

def _parse_one(value, conv, default_dayfirst=None):
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    if s.replace(".", "").isdigit():                 # Excel serial date
        n = float(s)
        if 20000 < n < 60000:
            return (datetime(1899, 12, 30) + timedelta(days=n)).strftime("%Y-%m-%d")
    m = AMBIG.match(s)
    dayfirst = False
    if m:
        decided = conv.get(m.group(2))
        if decided is None:
            decided = default_dayfirst                # None -> quarantine; True/False -> assume
        if decided is None:
            return None
        dayfirst = decided
    try:
        return dateparser.parse(s, dayfirst=dayfirst).strftime("%Y-%m-%d")
    except (ValueError, OverflowError):
        return None

# ============================ amounts & status ============================
def parse_amount(value):
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    s = re.sub(r"[^\d.\-]", "", s)                   # drop 'SGD', '$', commas, spaces
    try:
        return float(s)
    except ValueError:
        return None

def normalise_status(value):
    s = str(value).strip()
    return s.title() if s and s.lower() != "nan" else None

# ============================ categorical ============================
def matches_vocab(series, vocab, threshold=0.6):
    """fraction of DISTINCT non-empty values that are recognised members of vocab"""
    vals = {str(v).strip().lower() for v in series if _has_content(v)}
    if not vals:
        return False
    return sum(1 for v in vals if v in vocab) / len(vals) >= threshold

def normalise_subject(value):
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return None
    return subjects.get(s.lower(), s.title())     # known abbr -> full; unknown -> title-case

def consolidate_categorical(series, cutoff=90):
    vals = [str(v).strip() for v in series if _has_content(v)]
    counts = Counter(v.lower() for v in vals)
    display = {}
    for v in vals:
        display.setdefault(v.lower(), v)                     # representative original casing
    canon, cluster_of, reason_of = [], {}, {}
    for v in [k for k, _ in counts.most_common()]:           # frequent values first = anchors
        close = [c for c in canon if fuzz.ratio(v, c) >= cutoff]
        if not close:
            canon.append(v); cluster_of[v] = v
        elif len(close) == 1:
            cluster_of[v] = close[0]                          # spelling variant -> canonical
        else:
            cluster_of[v] = None
            reason_of[v] = f"ambiguous between '{display[close[0]]}' and '{display[close[1]]}'"
    totals = Counter()
    for v, n in counts.items():
        if cluster_of[v] is not None:
            totals[cluster_of[v]] += n
    for v in counts:                                         # singleton clusters -> flag
        tgt = cluster_of[v]
        if tgt is not None and totals[tgt] == 1:
            cluster_of[v] = None
            reason_of[v] = "only 1 occurrence"
    clean_value = {v: (display[cluster_of[v]] if cluster_of[v] is not None else None) for v in counts}
    return clean_value, reason_of

# ============================ column roles ============================
def _has_content(v):
    return str(v).strip() != "" and str(v).strip().lower() != "nan"

def looks_like_amount(series):
    cells = [str(v).strip() for v in series if _has_content(v)]
    if not cells:
        return False
    if any(re.search(r"(sgd|usd|rm|\$)", c.lower()) for c in cells):   # currency marker = strong signal
        return True
    nums = sorted(n for n in (parse_amount(c) for c in cells) if n is not None)
    if len(nums) < len(cells) * 0.6:        # column isn't really numeric
        return False
    return nums[len(nums) // 2] > 10        # median > 10 -> fee, not hours (fallback)

def _role(col_name, series):
    name = str(col_name).lower()
    if "date" in name:
        return "date"
    if "subject" in name or matches_vocab(series, subjects):
        return "subject"
    if looks_like_amount(series):
        return "amount"
    if is_categorical(series):
        return "categorical"
    return None

# ============================ main cleaner ============================
def clean_df(df, default_dayfirst=None):
    df = df.copy()

    # 1. strip whitespace from every cell (kills invisible trailing spaces)
    for col in df.columns:
        df[col] = df[col].map(lambda v: v.strip() if isinstance(v, str) else v)

    # 2. drop blank + decorative rows; keep rows with >= 2 populated fields
    df = df[df.apply(lambda r: sum(_has_content(v) for v in r) >= 2, axis=1)].reset_index(drop=True)

    original = df.copy()                              # stripped originals, for failure detection

    # 3. classify each column ONCE, before any values change
    roles = {col: _role(col, df[col]) for col in df.columns}

    # 4. normalise by role
    cat_maps = {}                                                    
    for col in df.columns:
        role = roles[col]
        if role == "date":
            df[col] = parse_column_dates(df[col], default_dayfirst)
        elif role == "amount":
            df[col] = df[col].map(parse_amount)
        elif role == "subject":                                   
            df[col] = df[col].map(normalise_subject)
        elif role == "categorical":                                
            cmap, creason = consolidate_categorical(df[col])
            cat_maps[col] = (cmap, creason)
            df[col] = df[col].map(lambda v, cmap=cmap:
                                  cmap.get(str(v).strip().lower(), v) if _has_content(v) else v)

# 5. quarantine rows where cleaning could not resolve a value
    codes, remarks = [], []
    for i in df.index:
        rc, rr = [], []
        for col in df.columns:
            role = roles[col]
            orig = original.at[i, col]
            if role in ("date", "amount") and _has_content(orig) and pd.isna(df.at[i, col]):
                rc.append("INVALID_TYPE")
                rr.append(f"{col}: {role} parse failed ('{orig}')")
            elif role == "categorical" and _has_content(orig):
                r = cat_maps[col][1].get(str(orig).strip().lower())
                if r:
                    rc.append("RARE_VALUE" if r == "only 1 occurrence" else "AMBIGUOUS_VALUE")
                    rr.append(f"{col}: {r} ('{orig}')")
        codes.append("|".join(dict.fromkeys(rc)))     # dedup, preserve order
        remarks.append("; ".join(rr))

    df["_reason_code"] = codes
    df["_remark"] = remarks
    quarantined = df[df["_reason_code"] != ""].reset_index(drop=True)
    clean = (df[df["_reason_code"] == ""]
             .drop(columns=["_reason_code", "_remark"]).reset_index(drop=True))
    return clean, quarantined