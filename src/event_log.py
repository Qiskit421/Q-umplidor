import json
import threading
from datetime import datetime, timezone
from pathlib import Path

# Tipos de evento
SYSTEM_STARTED = "SYSTEM_STARTED"
SYSTEM_STOPPED = "SYSTEM_STOPPED"
JOB_SUBMITTED = "JOB_SUBMITTED"                # trabajo aceptado -> QUEUED
JOB_STARTED = "JOB_STARTED"                    # un worker lo lanza -> RUNNING
JOB_FINISHED = "JOB_FINISHED"                  # terminó por sí solo (exit_code)
JOB_CANCEL_REQUESTED = "JOB_CANCEL_REQUESTED"  # el usuario pidió cancelar
JOB_CANCELLED = "JOB_CANCELLED"                # cancelación efectiva
JOB_REJECTED = "JOB_REJECTED"                  # comando inválido o sin recursos
JOB_INTERRUPTED = "JOB_INTERRUPTED"            # el sistema se cerró con el trabajo corriendo
ORPHAN_FILES_REMOVED = "ORPHAN_FILES_REMOVED"  # .out/.err sin trabajo borrados al arrancar
OUTPUT_FILES_CLEARED = "OUTPUT_FILES_CLEARED"  # queue clear borró salidas de trabajos terminados

class EventLog:
    def __init__(self, path="events.jsonl"):
        self._path = Path(path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq = max((e.get("seq", 0) for e in self.read()), default=0)

    def record(self, event, job_id=None, **details):
        """Agrega un evento a la bitácora y lo devuelve."""
        with self._lock:
            self._seq += 1
            entry = {
                "seq": self._seq,
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "event": event,
                "job_id": job_id,
                "details": details,
            }
            with self._path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            return entry

    def read(self, job_id=None, event=None, last=None):
        """Lee eventos, opcionalmente filtrando por trabajo/tipo o los últimos N.

        Ignora líneas corruptas (p. ej. una escritura cortada por un cierre abrupto).
        """
        entries = []
        if not self._path.exists():
            return entries
        with self._path.open(encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if job_id is not None and e.get("job_id") != job_id:
                    continue
                if event is not None and e.get("event") != event:
                    continue
                entries.append(e)
        return entries[-last:] if last else entries


def format_entry(e):
    """Una línea legible para la consola."""
    job = f" job={e['job_id']}" if e.get("job_id") is not None else ""
    det = "".join(f" {k}={v}" for k, v in e.get("details", {}).items())
    return f"{e['ts']} #{e['seq']} {e['event']}{job}{det}"