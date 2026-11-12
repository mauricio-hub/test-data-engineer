"""Eventos permitidos y auditoría compartida, sin dependencia del servicio de clientes."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def record_run(cursor: Any, run_id: str, read: int, loaded: int, result: str, *, rejected: int = 0,
               operation: str = "batch") -> None:
    """Añade auditoría con el cursor del llamador, sin confirmar su transacción."""
    if operation not in ("batch", "stream"):
        raise ValueError("Operación de auditoría no admitida.")
    cursor.execute("SELECT audit.record_run(%s,%s,%s,%s,%s,%s)", (run_id, operation, read, loaded, rejected, result))


def stream_event(*, consumed: int, counts: dict[str, int], duration: float,
                 reason: str | None = None, partition: int | None = None, offset: int | None = None) -> dict:
    """Construye un evento de streaming con conteos y ubicación técnica, sin mensajes crudos."""
    return {"event": "stream_failed" if reason else "stream_completed",
            "timestamp": datetime.now(timezone.utc).isoformat(), "eventos_consumidos": consumed,
            "alertas_por_tipo": counts, "duration_seconds": round(duration, 3),
            "reason": reason, "partition": partition, "offset": offset}



def client_event(*, rows_read: int = 0, rows_loaded: int = 0,
                 pii_clients: int = 0, reason: str | None = None, failed: bool = False) -> dict:
    """Construye el evento existente con conteos y un código ya validado, nunca datos crudos."""
    return {"event": "clients_failed" if failed else "clients_loaded",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": reason,
            "rows_read": rows_read,
            "rows_loaded": rows_loaded,
            "clientes_con_pii_en_texto_libre": pii_clients}


def batch_metrics(consumptions: dict, billing: dict, reasons: dict, durations: dict) -> dict:
    """Resume trabajo efectivo de consumos/facturas, separado de la calidad acumulada."""
    return {"timestamp": datetime.now(timezone.utc).isoformat(),
            "filas_leidas": consumptions["rows_read"] + billing["rows_read"],
            "filas_cargadas": consumptions["rows_loaded"] + billing["rows_loaded"],
            "filas_rechazadas_por_motivo": reasons,
            "archivos_rechazados": consumptions["files_rejected"] + billing["files_rejected"],
            "duracion_por_etapa_segundos": durations,
            "etapas": {"consumos": consumptions, "facturacion": billing}}
