"""Eventos permitidos y auditoría compartida, sin dependencia del servicio de clientes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def record_run(cursor: Any, run_id: str, read: int, loaded: int, result: str) -> None:
    """Añade auditoría con el cursor del llamador, sin confirmar su transacción."""
    cursor.execute("SELECT audit.record_run(%s,'batch',%s,%s,0,%s)", (run_id, read, loaded, result))



def client_event(*, rows_read: int = 0, rows_loaded: int = 0,
                 pii_clients: int = 0, reason: str | None = None, failed: bool = False) -> dict:
    """Construye el evento existente con conteos y un código ya validado, nunca datos crudos."""
    return {"event": "clients_failed" if failed else "clients_loaded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "rows_read": rows_read,
            "rows_loaded": rows_loaded,
            "clientes_con_pii_en_texto_libre": pii_clients}
