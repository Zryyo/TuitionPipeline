import io, uuid, json, logging
from datetime import datetime, timezone
import pandas as pd
from fastapi import FastAPI, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse
from logsetup import setup_logging, stage_log
from header import find_header
from etl import strip_blanks, header_from, finish_pipeline

setup_logging()                              # configure structured logging once at startup
app = FastAPI()
STORE   = {}                                 # upload_id -> {report, accepted, quarantine}; in-memory (use a DB for real)
PENDING = {}                                 # pending_id -> {cleared, filename}; headerless uploads awaiting names

def df_to_records(df):
    return json.loads(df.to_json(orient="records"))        # NaN -> null, handles dates/numbers

def samples_of(cleared, i, n=3):                            # column sample values, NaN -> None
    return [None if pd.isna(x) else x for x in cleared.iloc[:, i].head(n).tolist()]

def store_and_report(accepted, quarantine, uid, filename):
    report = {"upload_id": uid, "filename": filename,
              "uploaded_at": datetime.now(timezone.utc).isoformat(),
              "rows_total": len(accepted) + len(quarantine),
              "accepted": len(accepted), "quarantined": len(quarantine)}
    STORE[uid] = {"report": report, "accepted": accepted, "quarantine": quarantine}
    return report

@app.exception_handler(Exception)            # any uncaught error -> structured JSON, not a bare 500
async def all_errors(request, exc):
    return JSONResponse(status_code=500, content={"error": "internal_error", "message": str(exc)})

@app.post("/upload")
async def upload(file: UploadFile = File(...)):
    uid = uuid.uuid4().hex[:8]
    stage_log(logging.INFO, "upload", "file received", upload_id=uid, filename=file.filename)
    try:
        raw = pd.read_excel(io.BytesIO(await file.read()), header=None, dtype=str)
    except Exception as e:
        stage_log(logging.ERROR, "upload", "could not read file", upload_id=uid, filename=file.filename)
        raise HTTPException(status_code=400, detail={"error": "bad_file", "message": str(e)})

    cleared = strip_blanks(raw, upload_id=uid)
    result = find_header(cleared)

    if isinstance(result, list):                            # headerless -> ask the user for names
        PENDING[uid] = {"cleared": cleared, "filename": file.filename}
        stage_log(logging.INFO, "header", "headerless, awaiting names", upload_id=uid, inferred=result)
        return {"status": "needs_header", "pending_id": uid, "inferred": result,
                "samples": [samples_of(cleared, i) for i in range(cleared.shape[1])]}

    header, data = header_from(result, cleared)             # header found -> run straight through
    data.columns = header
    stage_log(logging.INFO, "header", "header detected", upload_id=uid, header_row=result)

    accepted, quarantine = finish_pipeline(data, upload_id=uid)
    return store_and_report(accepted, quarantine, uid, file.filename)

@app.post("/upload/{pending_id}/headers")                   # second request: user supplies the names
async def supply_headers(pending_id: str, headers: list[str]):
    if pending_id not in PENDING:
        raise HTTPException(status_code=404, detail={"error": "unknown_pending_id", "pending_id": pending_id})
    item = PENDING.pop(pending_id)
    cleared = item["cleared"]
    cleared.columns = headers
    stage_log(logging.INFO, "header", "headers supplied by user", upload_id=pending_id, headers=headers)

    accepted, quarantine = finish_pipeline(cleared, upload_id=pending_id)
    return store_and_report(accepted, quarantine, pending_id, item["filename"])

@app.get("/records")
def records(upload_id: str | None = Query(None)):
    if upload_id and upload_id not in STORE:
        raise HTTPException(status_code=404, detail={"error": "unknown_upload_id", "upload_id": upload_id})
    ids = [upload_id] if upload_id else list(STORE)
    out = [rec for i in ids for rec in df_to_records(STORE[i]["accepted"])]
    return {"count": len(out), "records": out}

@app.get("/quarantine")
def quarantine(upload_id: str | None = Query(None)):
    ids = [upload_id] if upload_id else list(STORE)
    out = [rec for i in ids if i in STORE for rec in df_to_records(STORE[i]["quarantine"])]
    return {"count": len(out), "quarantine": out}

@app.get("/report/{upload_id}")
def report(upload_id: str):
    if upload_id not in STORE:
        raise HTTPException(status_code=404, detail={"error": "unknown_upload_id", "upload_id": upload_id})
    return STORE[upload_id]["report"]

@app.get("/uploads")
def uploads():
    return {"count": len(STORE),
            "uploads": [v["report"] for v in STORE.values()]}

