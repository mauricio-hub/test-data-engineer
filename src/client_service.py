"""Conserva el flujo de clientes S02 y delega seguridad y observabilidad; no implementa ETL general."""
from __future__ import annotations

import base64
from contextlib import closing
import csv
from dataclasses import dataclass
import hashlib
import io
import json
from pathlib import Path
import re
import uuid

from typing import Any

from src import ROOT
from src.security import PrivacyError
from src.security.encryption import Cipher
from src.security.classification import Classification, SOURCE_COLUMNS
from src.security.masking import mask_pii
from src.observability import client_event, record_run


@dataclass(frozen=True)
class ClientResult:
    """Resume cantidades de la carga sin contener filas ni información personal."""
    rows_read: int
    rows_loaded: int
    pii_clients: int


def parse_clients(data: bytes) -> list[dict[str, str]]:
    """Lee y valida el maestro completo, conservando registros lógicos y textos largos."""
    try:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        csv.field_size_limit(2**31 - 1)
        reader = csv.DictReader(io.StringIO(text, newline=""), strict=True)
        if tuple(reader.fieldnames or ()) != SOURCE_COLUMNS:
            raise PrivacyError("csv_invalid")
        rows = list(reader)
        if not rows or any(set(row) != set(SOURCE_COLUMNS) or any(v is None for v in row.values()) for row in rows):
            raise PrivacyError("csv_invalid")
        identifiers = set()
        for row in rows:
            if not re.fullmatch(r"CLI[0-9]{4}", row["cliente_id"]):
                raise PrivacyError("client_id_invalid")
            if row["cliente_id"] in identifiers:
                raise PrivacyError("client_duplicate")
            identifiers.add(row["cliente_id"])
        return rows
    except PrivacyError:
        raise
    except Exception:
        raise PrivacyError("csv_invalid") from None


def protect_client(row: dict[str, str], policy: Classification, cipher: Cipher) -> tuple[dict, bool]:
    """Protege una copia del cliente y señala si sus observaciones contenían PII."""
    values = dict(row)
    values["observaciones"], detected = mask_pii(values["observaciones"])
    identifier = values["cliente_id"]
    for column in SOURCE_COLUMNS:
        values[column] = policy.protect("core.clientes", column, values[column],
                                       f"core.clientes:{identifier}:{column}", cipher)
    return values, detected


def ingest_bytes(connection: Any, data: bytes, policy: Classification, cipher: Cipher) -> ClientResult:
    """Todo SQL recibe parámetros; solo identificadores constantes forman el SQL."""
    digest = hashlib.sha256(data).hexdigest()
    run_id = str(uuid.uuid4())
    policy.validate_database(connection)
    # Detectar llave equivocada antes de omitir filas existentes o recifrarlas.
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT cliente_id,razon_social FROM core.clientes LIMIT 1")
            existing = cursor.fetchone()
            if existing:
                cipher.open(existing[1], f"core.clientes:{existing[0]}:razon_social")
            cursor.execute("SELECT source_sha256,record_number,reason,payload FROM core.clientes_cuarentena LIMIT 1")
            rejected = cursor.fetchone()
            if rejected:
                cipher.open(rejected[3], f"core.clientes_cuarentena:{rejected[0]}:{rejected[1]}:{rejected[2]}")
    except PrivacyError:
        raise
    except Exception:
        raise PrivacyError("database_error") from None
    try:
        rows = parse_clients(data)
    except PrivacyError as error:
        try:
            # Archivo rechazado completo: fila lógica 0 y contenido íntegro cifrado.
            payload = policy.protect("core.clientes_cuarentena", "payload",
                                     base64.b64encode(data).decode("ascii"),
                                     f"core.clientes_cuarentena:{digest}:0:{error.code}", cipher)
            with connection.cursor() as cursor:
                cursor.execute("INSERT INTO core.clientes_cuarentena VALUES (%s,0,%s,%s) "
                               "ON CONFLICT DO NOTHING", (digest, error.code, payload))
                record_run(cursor, run_id, 0, 0, "rejected")
            connection.commit()
        except Exception:
            try:
                connection.rollback()
            except Exception:
                pass
            raise PrivacyError("database_error") from None
        raise
    protected = [protect_client(row, policy, cipher) for row in rows]
    loaded = 0
    # Los nombres siguientes proceden de constantes internas, nunca de archivos.
    columns = SOURCE_COLUMNS + ("observaciones_con_pii", "source_sha256")
    assignments = ",".join(f"{c}=EXCLUDED.{c}" for c in columns if c != "cliente_id")
    statement = (f"INSERT INTO core.clientes ({','.join(columns)}) VALUES ({','.join(['%s']*len(columns))}) "
                 f"ON CONFLICT (cliente_id) DO UPDATE SET {assignments} "
                 "WHERE core.clientes.source_sha256 IS DISTINCT FROM EXCLUDED.source_sha256")
    try:
        with connection.cursor() as cursor:
            for values, detected in protected:
                cursor.execute(statement, tuple(values[c] for c in SOURCE_COLUMNS) + (detected, digest))
                loaded += cursor.rowcount
            record_run(cursor, run_id, len(rows), loaded, "success")
        connection.commit()
    except Exception:
        # Deshacer toda la carga; el registro de fallo es otra transacción.
        try:
            connection.rollback()
            with connection.cursor() as cursor:
                record_run(cursor, run_id, len(rows), 0, "failed")
            connection.commit()
        except Exception:
            pass  # El error principal sigue siendo fallo; nunca se informa éxito.
        raise PrivacyError("database_error") from None
    return ClientResult(len(rows), loaded, sum(detected for _, detected in protected))


def connect_operational() -> Any:
    """Abre la conexión del rol ingesta con la configuración local existente."""
    try:
        import psycopg2
        config = json.loads((ROOT / ".local/ingesta.json").read_text(encoding="utf-8"))
        if config["usuario"] != "rol_ingesta" or config["host"] != "127.0.0.1" or config["database"] != "bia_datos":
            raise ValueError
        return psycopg2.connect(host=config["host"], port=int(config["port"]), dbname=config["database"],
                                user=config["usuario"], password=config["password"], connect_timeout=5)
    except Exception:
        raise PrivacyError("database_error") from None


def safe_event(result: ClientResult | None, error: PrivacyError | None) -> dict:
    """Adapta el resultado público de clientes a campos simples de observabilidad."""
    return client_event(
        rows_read=result.rows_read if result else 0,
        rows_loaded=result.rows_loaded if result else 0,
        pii_clients=result.pii_clients if result else 0,
        reason=error.code if error else None,
        failed=bool(error),
    )


def main(*, source: Path = ROOT / "data/maestros/clientes.csv",
         log_path: Path = ROOT / "logs/pipeline.log") -> int:
    """Coordina clientes y registra un resultado seguro; devuelve cero solo si termina bien."""
    result = None
    error = None
    try:
        cipher = Cipher.from_env()
        policy = Classification.load()
        try:
            data = source.read_bytes()
        except OSError:
            raise PrivacyError("source_unavailable") from None
        with closing(connect_operational()) as connection:
            result = ingest_bytes(connection, data, policy, cipher)
    except PrivacyError as caught:
        error = caught
    except Exception:
        error = PrivacyError("internal_error")
    event = safe_event(result, error)
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
    except OSError:
        print(json.dumps(safe_event(None, PrivacyError("internal_error"))))
        return 1
    print(json.dumps(event))
    return 1 if error else 0


