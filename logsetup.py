import logging, json, sys
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self, record):
        ctx = dict(getattr(record, "context", {}))          # caller's stage + identifiers
        entry = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "stage": ctx.pop("stage", None),
            "message": record.getMessage(),
        }
        entry.update(ctx)                                    # remaining identifiers
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info).splitlines()[-1]
        return json.dumps(entry, default=str)

def setup_logging(level=logging.INFO):
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear(); root.addHandler(h); root.setLevel(level)

_logger = logging.getLogger("pipeline")

def stage_log(level, stage, message, exc_info=False, **identifiers):
    """one structured log line: level, timestamp, stage, message + any identifiers"""
    _logger.log(level, message, extra={"context": {"stage": stage, **identifiers}}, exc_info=exc_info)