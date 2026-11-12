"""Coordina ingesta, facturación y publicación del recorrido batch completo."""
from __future__ import annotations

from contextlib import closing
import json
from pathlib import Path
from time import perf_counter
from datetime import datetime, timezone
from typing import Any
import uuid

from src import ROOT
from src.batch.extract import discover
from src.batch.load import ingest_file, load_masters, ingest_billing, report_context, rejection_counts
from src.client_service import connect_operational, ingest_bytes
from src.observability import record_run, batch_metrics
from src.quality.reports import quality_report, monthly_csv, publish
from src.security import PrivacyError
from src.security.classification import Classification
from src.security.encryption import Cipher


def run(connection: Any, source: Path, policy: Classification, cipher: Cipher,
        batch_size: int = 1000) -> dict[str, int]:
    """Carga clientes con S02, maestros pendientes y todos los consumos descubiertos."""
    if not 1 <= batch_size <= 10000:
        raise ValueError("Tamaño de lote no permitido.")
    totals = {"rows_read": 0, "rows_loaded": 0, "rows_rejected": 0, "files_rejected": 0}
    run_id = str(uuid.uuid4())
    try:
        ingest_bytes(connection, (source / "maestros/clientes.csv").read_bytes(), policy, cipher)
        load_masters(connection, (source / "maestros/fronteras.csv").read_bytes(),
                     (source / "maestros/limites_frontera.csv").read_bytes(), policy)
        for path in discover(source / "consumos"):
            counts = ingest_file(connection, path.name, path.read_bytes(), policy, cipher, batch_size)
            for key in totals:
                totals[key] += counts[key]
        with connection.cursor() as cursor:
            record_run(cursor, run_id, totals["rows_read"], totals["rows_loaded"],
                       "rejected" if totals["files_rejected"] else "success", rejected=totals["rows_rejected"])
        connection.commit()
    except Exception:
        connection.rollback()
        try:
            with connection.cursor() as cursor:
                # Los archivos ya confirmados se conservan; el siguiente intento puede continuar.
                record_run(cursor, run_id, totals["rows_read"], totals["rows_loaded"], "failed",
                           rejected=totals["rows_rejected"])
            connection.commit()
        except Exception:
            connection.rollback()
        raise
    return totals


def main(*, config_path: Path = ROOT / "config/pipeline.yaml",
         log_path: Path = ROOT / "logs/pipeline.log", output_path: Path = ROOT / "out") -> int:
    """Ejecuta el batch completo con llave explícita y eventos sin contenido personal."""
    start = perf_counter()
    event = {"event": "batch_completed", "timestamp": datetime.now(timezone.utc).isoformat()}
    failed = False
    try:
        import yaml
        cipher = Cipher.from_env()
        policy = Classification.load(include_billing=True)
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        source = ROOT / config["origen"]["ruta"]
        with closing(connect_operational()) as connection:
            event.update(run_full(connection, source, output_path, policy, cipher, int(config["pipeline"]["batch_size"])))
    except Exception as error:
        failed = True
        event.update(event="batch_failed", reason=error.code if isinstance(error, PrivacyError) else "internal_error")
    event["duration_seconds"] = round(perf_counter() - start, 3)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
    except OSError:
        failed = True
        event = {"event": "batch_failed", "reason": "internal_error"}
    print(json.dumps(event))
    return int(failed)


def run_full(connection: Any, source: Path, output: Path, policy: Classification,
             cipher: Cipher, batch_size: int = 1000) -> dict:
    """Reutiliza S03 sin cambiar su interfaz y publica resultados del conjunto confirmado."""
    run_id = str(uuid.uuid4())
    consumed = {"rows_read": 0, "rows_loaded": 0, "rows_rejected": 0, "files_rejected": 0}
    billed = dict(consumed)
    try:
        policy.validate_database(connection, tuple(policy.tables))
        before = rejection_counts(connection)
        start = perf_counter()
        consumed = run(connection, source, policy, cipher, batch_size)
        durations = {"ingesta_consumos": round(perf_counter() - start, 6)}
        start = perf_counter()
        for path in discover(source / "facturacion"):
            counts = ingest_billing(connection, path.name, path.read_bytes(), policy, cipher)
            for key in billed:
                billed[key] += counts[key]
        durations["facturacion"] = round(perf_counter() - start, 6)
        start = perf_counter()
        context = report_context(connection)
        quality = quality_report(source, context)
        csv_output = monthly_csv(context["monthly"])
        durations["calidad_y_agregacion"] = round(perf_counter() - start, 6)
        reasons = {reason: count - before.get(reason, 0) for reason, count in context["rejections"].items()
                   if count > before.get(reason, 0)}
        metrics = batch_metrics(consumed, billed, reasons, durations)
        publish(output, csv_output, quality, metrics)
        with connection.cursor() as cursor:
            record_run(cursor, run_id, metrics["filas_leidas"], metrics["filas_cargadas"],
                       "rejected" if metrics["archivos_rechazados"] else "success",
                       rejected=consumed["rows_rejected"] + billed["rows_rejected"])
        connection.commit()
        return metrics
    except Exception:
        connection.rollback()
        try:
            with connection.cursor() as cursor:
                record_run(cursor, run_id, consumed["rows_read"] + billed["rows_read"],
                           consumed["rows_loaded"] + billed["rows_loaded"], "failed",
                           rejected=consumed["rows_rejected"] + billed["rows_rejected"])
            connection.commit()
        except Exception:
            connection.rollback()
        raise


if __name__ == "__main__":
    raise SystemExit(main())
