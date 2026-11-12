"""Persiste maestros, consumos y facturación con transacciones y SQL parametrizado."""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Any
import uuid

from psycopg2.extras import execute_values

from src.batch.extract import InputError, read_csv, read_billing
from src.batch.transform import normalize, normalize_billing
from src.observability import record_run
from src.security import PrivacyError
from src.security.classification import Classification, MODEL, BILLING_MODEL
from src.security.encryption import Cipher

BATCH_TABLES = tuple(name for name in MODEL if name.startswith("core.") and name not in ("core.clientes", "core.clientes_cuarentena"))
FRONTIER_COLUMNS = ("frontera_id", "codigo_sic", "cliente_id", "mercado", "operador_red", "nivel_tension", "fecha_registro", "estado")
LIMIT_COLUMNS = ("frontera_id", "min_kwh", "max_kwh")


def load_masters(connection: Any, frontiers: bytes, limits: bytes, policy: Classification) -> None:
    """Carga maestros inmutables sin actualizar ni borrar fronteras existentes."""
    try:
        policy.validate_database(connection, BATCH_TABLES)
        frontier_rows, limit_rows = read_csv(frontiers), read_csv(limits)
        if set(frontier_rows[0]) != set(FRONTIER_COLUMNS) or set(limit_rows[0]) != set(LIMIT_COLUMNS):
            raise InputError()
        with connection.cursor() as cursor:
            execute_values(cursor, "INSERT INTO core.fronteras VALUES %s ON CONFLICT DO NOTHING",
                           [tuple(row[column] for column in FRONTIER_COLUMNS) for row in frontier_rows])
            execute_values(cursor, "INSERT INTO core.limites_frontera VALUES %s ON CONFLICT DO NOTHING",
                           [tuple(row[column] for column in LIMIT_COLUMNS) for row in limit_rows])
        connection.commit()
    except Exception:
        connection.rollback()
        raise PrivacyError("database_error") from None


def quarantine_invoice(cursor: Any, name: str, digest: str, number: int, reason: str,
                       evidence: str, policy: Classification, cipher: Cipher) -> None:
    """Cifra la evidencia completa de facturación antes de enviarla a PostgreSQL."""
    context = json.dumps(["billing", name, digest, number, reason], ensure_ascii=True)
    protected = policy.protect("core.facturas_cuarentena", "payload", evidence, context, cipher)
    cursor.execute("INSERT INTO core.facturas_cuarentena VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                   (name, digest, number, reason, protected))


def ingest_billing(connection: Any, name: str, data: bytes, policy: Classification, cipher: Cipher) -> dict:
    """Carga facturas y componentes por archivo; las huérfanas se conservan cifradas."""
    digest, run_id = hashlib.sha256(data).hexdigest(), str(uuid.uuid4())
    counts = {"rows_read": 0, "rows_loaded": 0, "rows_rejected": 0, "files_rejected": 0}
    try:
        policy.validate_database(connection, tuple(BILLING_MODEL))
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(83103)")
            cursor.execute("SELECT source_sha256,estado FROM core.archivos_facturacion WHERE archivo=%s", (name,))
            previous = cursor.fetchone()
            if previous and previous[0] == digest:
                counts["files_rejected"] = int(previous[1] == "rejected")
                record_run(cursor, run_id, 0, 0, "rejected" if counts["files_rejected"] else "success")
                connection.commit()
                return counts
            try:
                if previous:
                    raise InputError("changed_file")
                document = read_billing(data)
                invoices = normalize_billing(document)
                cursor.execute("SELECT factura_id FROM core.facturas WHERE factura_id=ANY(%s)", ([row["id"] for row in invoices],))
                if cursor.fetchone():
                    raise InputError()
            except InputError as error:
                cursor.execute("INSERT INTO core.archivos_facturacion VALUES (%s,%s,'rejected',0,0) ON CONFLICT DO NOTHING", (name, digest))
                quarantine_invoice(cursor, name, digest, 0, error.reason,
                                   base64.b64encode(data).decode("ascii"), policy, cipher)
                record_run(cursor, run_id, 0, 0, "rejected")
                connection.commit()
                counts["files_rejected"] = 1
                return counts
            cursor.execute("SELECT frontera_id FROM core.fronteras")
            known = {row[0] for row in cursor.fetchall()}
            rejected = sum(row["frontier"] not in known for row in invoices)
            counts.update(rows_read=len(invoices), rows_rejected=rejected)
            cursor.execute("INSERT INTO core.archivos_facturacion VALUES (%s,%s,'applied',%s,%s)",
                           (name, digest, len(invoices), rejected))
            for number, row in enumerate(invoices, 1):
                if row["frontier"] not in known:
                    quarantine_invoice(cursor, name, digest, number, "orphan_invoice",
                                       json.dumps({"periodo": document["periodo"], "emisor": document.get("emisor"),
                                                   "generado_en": document.get("generado_en"), "factura": row["raw"]}, default=str), policy, cipher)
                    continue
                payload = policy.protect("core.facturas", "payload", json.dumps(row["private"], default=str),
                                         "core.facturas:" + row["id"], cipher)
                cursor.execute("INSERT INTO core.facturas VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                               (row["id"], row["frontier"], row["period"], *row["amounts"], name, payload))
                for position, (amount, private) in enumerate(row["components"], 1):
                    payload = policy.protect("core.factura_componentes", "payload", json.dumps(private, default=str),
                                             f"core.factura_componentes:{row['id']}:{position}", cipher)
                    cursor.execute("INSERT INTO core.factura_componentes VALUES (%s,%s,%s,%s)",
                                   (row["id"], position, amount, payload))
                counts["rows_loaded"] += 1
            record_run(cursor, run_id, len(invoices), counts["rows_loaded"], "success", rejected=rejected)
        connection.commit()
        return counts
    except Exception:
        connection.rollback()
        try:
            with connection.cursor() as cursor:
                record_run(cursor, run_id, counts["rows_read"], 0, "failed")
            connection.commit()
        except Exception:
            connection.rollback()
        raise PrivacyError("database_error") from None


def report_context(connection: Any) -> dict:
    """Consulta agregados y metadatos confirmados; no obtiene texto personal ni componentes."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT frontera_id,mes,consumo_kwh,horas_con_dato FROM analytics.v_consumo_mensual ORDER BY frontera_id,mes")
        monthly = cursor.fetchall()
        cursor.execute("SELECT frontera_id FROM core.fronteras ORDER BY frontera_id")
        frontiers = [row[0] for row in cursor.fetchall()]
        cursor.execute("SELECT archivo,source_sha256 FROM core.archivos_ingesta WHERE estado='applied' ORDER BY archivo COLLATE \"C\"")
        files = cursor.fetchall()
        cursor.execute("SELECT count(*) FROM core.facturas_cuarentena WHERE motivo='orphan_invoice'")
        orphans = cursor.fetchone()[0]
        cursor.execute("SELECT count(*) FROM core.clientes WHERE observaciones_con_pii")
        pii_clients = cursor.fetchone()[0]
    return {"monthly": monthly, "frontiers": frontiers, "files": files,
            "orphans": orphans, "pii_clients": pii_clients, "rejections": rejection_counts(connection)}


def rejection_counts(connection: Any) -> dict[str, int]:
    """Cuenta motivos técnicos sin leer payloads cifrados ni datos personales."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT reason,count(*) FROM (SELECT motivo AS reason FROM core.consumos_cuarentena "
                       "UNION ALL SELECT motivo FROM core.facturas_cuarentena) q GROUP BY reason")
        return dict(cursor.fetchall())


def quarantine(cursor: Any, name: str, digest: str, number: int, reason: str,
               evidence: str, policy: Classification, cipher: Cipher) -> None:
    """Cifra evidencia antes del INSERT; repetir no reemplaza el cifrado ya guardado."""
    context = json.dumps([name, digest, number, reason], ensure_ascii=True)
    payload = policy.protect("core.consumos_cuarentena", "payload", evidence, context, cipher)
    cursor.execute("INSERT INTO core.consumos_cuarentena VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                   (name, digest, number, reason, payload))


def ingest_file(connection: Any, name: str, data: bytes, policy: Classification,
                cipher: Cipher, batch_size: int = 1000) -> dict[str, int]:
    """Aplica un archivo completo; conserva ganadores inválidos y aísla rechazos estructurales."""
    run_id = str(uuid.uuid4())
    digest = hashlib.sha256(data).hexdigest()
    counts = {"rows_read": 0, "rows_loaded": 0, "rows_rejected": 0, "files_rejected": 0}
    try:
        policy.validate_database(connection, BATCH_TABLES)
        with connection.cursor() as cursor:
            # Serializa escritores de S03 sin privilegios administrativos ni tablas temporales.
            cursor.execute("SELECT pg_advisory_xact_lock(83103)")
            cursor.execute("SELECT source_sha256,estado FROM core.archivos_ingesta WHERE archivo=%s", (name,))
            existing = cursor.fetchone()
            if existing and existing[0] == digest:
                rejected = existing[1] == "rejected"
                counts["files_rejected"] = int(rejected)
                record_run(cursor, run_id, 0, 0, "rejected" if rejected else "success")
                connection.commit()
                return counts
            try:
                if existing:
                    raise InputError("changed_file")
                rows = read_csv(data)
                readings = normalize(rows)
                cursor.execute("SELECT frontera_id FROM core.fronteras")
                known = {row[0] for row in cursor.fetchall()}
                if any(reading.frontier not in known for reading in readings):
                    raise InputError()
            except InputError as error:
                cursor.execute("INSERT INTO core.archivos_ingesta VALUES (%s,%s,'rejected',0,0) ON CONFLICT DO NOTHING", (name, digest))
                quarantine(cursor, name, digest, 0, error.reason, base64.b64encode(data).decode("ascii"), policy, cipher)
                record_run(cursor, run_id, 0, 0, "rejected")
                connection.commit()
                counts["files_rejected"] = 1
                return counts

            counts["rows_read"] = len(readings)
            counts["rows_rejected"] = sum(reading.reason is not None for reading in readings)
            cursor.execute("INSERT INTO core.archivos_ingesta VALUES (%s,%s,'applied',%s,%s)",
                           (name, digest, len(readings), counts["rows_rejected"]))
            winners = {}
            for reading, raw in zip(readings, rows):
                key = (reading.frontier, reading.timestamp)
                previous = winners.get(key)
                if previous is None or (reading.version, reading.number) > (previous.version, previous.number):
                    winners[key] = reading
                if reading.reason:
                    quarantine(cursor, name, digest, reading.number, reading.reason,
                               json.dumps(raw, ensure_ascii=False), policy, cipher)
            changed = execute_values(cursor,
                "INSERT INTO core.estado_lectura AS current (frontera_id,timestamp,version_lectura,archivo,fila,valida) VALUES %s "
                "ON CONFLICT (frontera_id,timestamp) DO UPDATE SET version_lectura=EXCLUDED.version_lectura,"
                "archivo=EXCLUDED.archivo,fila=EXCLUDED.fila,valida=EXCLUDED.valida "
                "WHERE (EXCLUDED.version_lectura,EXCLUDED.archivo,EXCLUDED.fila) > "
                "(current.version_lectura,current.archivo,current.fila) RETURNING frontera_id,timestamp,valida",
                [(r.frontier, r.timestamp, r.version, name, r.number, r.reason is None) for r in winners.values()],
                page_size=batch_size, fetch=True)
            valid = [winners[(frontier, stamp)] for frontier, stamp, accepted in changed if accepted]
            invalid = [(frontier, stamp) for frontier, stamp, accepted in changed if not accepted]
            if valid:
                execute_values(cursor,
                    "INSERT INTO core.fact_consumo_horario VALUES %s ON CONFLICT (frontera_id,timestamp) "
                    "DO UPDATE SET consumo_kwh=EXCLUDED.consumo_kwh,calidad_lectura=EXCLUDED.calidad_lectura",
                    [(r.frontier, r.timestamp, r.kwh, r.quality) for r in valid], page_size=batch_size)
            if invalid:
                # A01: retirar solo las claves ganadas por una corrección inválida, nunca reconstruir tablas.
                execute_values(cursor,
                    "DELETE FROM core.fact_consumo_horario f USING (VALUES %s) AS gone(frontier,stamp) "
                    "WHERE f.frontera_id=gone.frontier AND f.timestamp=gone.stamp", invalid, page_size=batch_size)
            counts["rows_loaded"] = len(valid)
            record_run(cursor, run_id, len(readings), len(valid), "success", rejected=counts["rows_rejected"])
        connection.commit()
        return counts
    except Exception:
        connection.rollback()
        try:
            with connection.cursor() as cursor:
                record_run(cursor, run_id, counts["rows_read"], 0, "failed")
            connection.commit()
        except Exception:
            connection.rollback()
        raise PrivacyError("database_error") from None
