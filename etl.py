import pandas as pd
from rapidfuzz import fuzz
import re
from datetime import datetime, timedelta
from dateutil import parser as dateparser
from collections import Counter
from header import load, find_header
from cleaner import clean_df
from validator import validate_df
import logging
from logsetup import stage_log
REQUIRED_COLS = ['Assignment ID', 'Tutor Name', 'Student Name', 'Hourly Rate (SGD)' ,'Start Date' , 
                 'Status', 'Contact Email', 'Log ID', 'Date', 'Hours', 'Attendance', 
                 'Invoice ID', 'Tutor ID', 'Invoice Date', 'Amount', 'Payment Status']
UNIQUE_KEYS = [['Log ID'], ['Invoice ID'], ['Assignment ID']]
#================================== MAIN ====================================

def strip_blanks(raw_df, upload_id=None):
    cleared = raw_df[raw_df.apply(lambda r: r.astype(str).str.strip().ne("").any(), axis=1)].reset_index(drop=True)
    stage_log(logging.INFO, "load", "blank rows removed",
              upload_id=upload_id, rows_in=len(raw_df), rows_out=len(cleared))
    return cleared

def header_from(result, cleared):
    """int result -> (header list, data with the header row removed)"""
    header = [str(c).strip() for c in cleared.iloc[result]]
    data = cleared.iloc[result + 1:].reset_index(drop=True)
    return header, data

def finish_pipeline(data, upload_id=None):
    """data already has its .columns set. Runs clean -> validate, with logging."""
    cleaned_df, flagged = clean_df(data)
    stage_log(logging.INFO, "clean", "cleaning complete",
              upload_id=upload_id, clean_rows=len(cleaned_df), flagged_rows=len(flagged))

    accepted, quarantine = validate_df(cleaned_df, flagged, REQUIRED_COLS, UNIQUE_KEYS)
    stage_log(logging.WARNING if len(quarantine) else logging.INFO, "validate", "validation complete",
              upload_id=upload_id, accepted=len(accepted), quarantined=len(quarantine))
    return accepted, quarantine
