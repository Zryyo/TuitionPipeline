import pandas as pd
from rapidfuzz import fuzz
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from collections import Counter
from cleaner import _has_content


# ============================ validator ============================

def _quarantine_row(df, i, code, remark):
    """Original row + the two reporting columns."""
    r = df.loc[i].copy()
    r["_reason_code"] = code
    r["_remark"] = remark
    return r


def _check_required(df, required_cols):
    present = [c for c in required_cols if c in df.columns]   # only enforce what's here
    keep, quarantined = [], []
    for i in df.index:
        missing = [c for c in present if not _has_content(df.at[i, c])]
        if missing:
            remark = f"{', '.join(missing)} is required but empty"
            quarantined.append(_quarantine_row(df, i, "MISSING_REQUIRED", remark))
        else:
            keep.append(i)
    return df.loc[keep], quarantined


def _check_exact_duplicates(df, ignore_cols=()):
    """Duplicate = identical across all columns EXCEPT the ignored ones (e.g. the surrogate ID)."""
    compare = [c for c in df.columns if not str(c).startswith("_") and c not in ignore_cols]
    dup_mask = df.duplicated(subset=compare, keep="first")
    quarantined = [
        _quarantine_row(df, i, "DUPLICATE_ROW",
                        f"Identical to an earlier row apart from {', '.join(ignore_cols)} — removed")
        for i in df.index[dup_mask]
    ]
    return df[~dup_mask], quarantined


def _check_unique(df, unique_keys):
    quarantined, drop = [], set()
    for key_cols in unique_keys:                      # each key is a list of columns
        cols = [c for c in key_cols if c in df.columns]
        if not cols:
            continue
        clash_mask = df.duplicated(subset=cols, keep=False)
        for i in df.index[clash_mask]:
            vals = ", ".join(f"{c}={df.at[i, c]!r}" for c in cols)
            remark = f"Two records share {', '.join(cols)} ({vals}) but differ — needs review"
            quarantined.append(_quarantine_row(df, i, "IDENTITY_CONFLICT", remark))
            drop.add(i)
    return df.drop(index=drop), quarantined

def _pick_key(df, unique_keys):
    present = [k for k in unique_keys if all(c in df.columns for c in k)]
    if not present:
        return None
    cols = list(df.columns)
    return min(present, key=lambda k: min(cols.index(c) for c in k))   # leftmost column in the file wins

def validate_df(clean, quarantine, required_cols, unique_keys):
    q_rows = []
    clean, q = _check_required(clean, required_cols);             q_rows += q
    key = _pick_key(clean, unique_keys)                  # ONE key wins, by priority
    ignore = key if key else []                                  # ignore only that key in dedup
    clean, q = _check_exact_duplicates(clean, ignore_cols=ignore); q_rows += q
    if key:
        clean, q = _check_unique(clean, [key]);                  q_rows += q
    if q_rows:
        quarantine = pd.concat([quarantine, pd.DataFrame(q_rows)], ignore_index=True)
    return clean.reset_index(drop=True), quarantine