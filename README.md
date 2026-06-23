# ETL Tech Assessment

A FastAPI-based ETL pipeline for cleaning and validating tutoring operations data — lesson logs, tutor assignments, and invoices — uploaded as Excel files.

## What it does

1. **Ingests** `.xlsx` files via a REST endpoint
2. **Detects headers** automatically (vocabulary matching + block-structure heuristics); if no header is found, asks the caller to supply column names
3. **Cleans** each column by inferred role:
   - `date` — parses ambiguous date formats, resolves day-first vs month-first per column
   - `amount` — strips currency symbols, returns a float
   - `status` — title-cases the value
   - `subject` — maps abbreviations to canonical subject names
   - `categorical` — fuzzy-clusters spelling variants; flags singletons and ambiguous values
4. **Validates** cleaned rows for required fields, exact duplicates, and unique-key conflicts
5. **Returns** two sets: accepted clean records and a quarantine set with reason codes and remarks

---

## Requirements

- Python 3.10+

### Dependencies

```
fastapi
uvicorn[standard]
python-multipart
pandas
openpyxl
rapidfuzz
python-dateutil
```

---

## Setup

```bash
# 1. Create and activate a virtual environment (recommended)
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt
```

---

## Running the API

```bash
uvicorn api:app --reload
```

The server starts at `http://127.0.0.1:8000`. The `--reload` flag restarts on file changes (dev only).

Interactive docs are available at:
- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`

---

## API Endpoints

### `POST /upload`
Upload an Excel file for processing.

```bash
curl -X POST http://127.0.0.1:8000/upload \
  -F "file=@lesson_logs_messy.xlsx"
```

**Response — header detected:**
```json
{
  "upload_id": "a1b2c3d4",
  "filename": "lesson_logs_messy.xlsx",
  "uploaded_at": "2026-06-23T10:00:00+00:00",
  "rows_total": 120,
  "accepted": 115,
  "quarantined": 5
}
```

**Response — no header found (`needs_header`):**
```json
{
  "status": "needs_header",
  "pending_id": "e5f6g7h8",
  "inferred": ["categorical: Active,Inactive", "col_1", "..."],
  "samples": [["Active", "Active", "Inactive"], ...]
}
```

---

### `POST /upload/{pending_id}/headers`
Supply column names for a headerless upload. Use the `pending_id` from the `needs_header` response. Send a JSON array of strings matching the number of columns.

```bash
curl -X POST http://127.0.0.1:8000/upload/e5f6g7h8/headers \
  -H "Content-Type: application/json" \
  -d '["Status", "Tutor Name", "Student Name", "Date", "Hours"]'
```

---

### `GET /records`
Retrieve all accepted clean records, optionally filtered by upload.

```bash
# All uploads
curl http://127.0.0.1:8000/records

# Single upload
curl "http://127.0.0.1:8000/records?upload_id=a1b2c3d4"
```

---

### `GET /quarantine`
Retrieve all quarantined rows with reason codes and remarks.

```bash
curl http://127.0.0.1:8000/quarantine

# Reason codes: INVALID_TYPE | RARE_VALUE | AMBIGUOUS_VALUE |
#               MISSING_REQUIRED | DUPLICATE_ROW | IDENTITY_CONFLICT
```

---

### `GET /report/{upload_id}`
Summary report for a specific upload.

```bash
curl http://127.0.0.1:8000/report/a1b2c3d4
```

```json
{
  "upload_id": "a1b2c3d4",
  "filename": "lesson_logs_messy.xlsx",
  "uploaded_at": "2026-06-23T10:00:00+00:00",
  "rows_total": 120,
  "accepted": 115,
  "quarantined": 5
}
```

---

### `GET /uploads`
List all uploads processed in the current session.

```bash
curl http://127.0.0.1:8000/uploads
```

---

## File structure

```
.
├── api.py          # FastAPI app and route handlers
├── etl.py          # Pipeline orchestration (strip → header → clean → validate)
├── header.py       # Header detection and column labelling
├── cleaner.py      # Per-role normalisation (dates, amounts, categoricals)
├── validator.py    # Required-field, duplicate, and unique-key checks
├── logsetup.py     # Structured JSON logging
└── requirements.txt
```

---

## Quarantine reason codes

| Code | Cause |
|---|---|
| `INVALID_TYPE` | Date or amount cell could not be parsed |
| `RARE_VALUE` | Categorical value appears only once (likely a typo) |
| `AMBIGUOUS_VALUE` | Categorical value fuzzy-matches two different canonical values |
| `MISSING_REQUIRED` | A required column is present but empty for this row |
| `DUPLICATE_ROW` | Row is identical to an earlier row |
| `IDENTITY_CONFLICT` | Two rows share a unique key (Log ID / Invoice ID / Assignment ID) but differ in other fields |
