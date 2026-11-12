"""Tres escenarios críticos S03 sobre PostgreSQL real y una base temporal propia."""
from __future__ import annotations

from contextlib import closing, redirect_stdout
import hashlib
import io
import json
from pathlib import Path
import re
import tempfile
from typing import Any
import unittest
from unittest.mock import patch
import uuid

from cryptography.fernet import Fernet
import psycopg2
from psycopg2 import sql

from src import ROOT
from src.batch.extract import discover, read_csv
from src.batch.transform import normalize
from src.batch.load import ingest_file, load_masters
from src.batch.pipeline import main, run
from src.client_service import ingest_bytes
from src.security import PrivacyError
from src.security.classification import Classification
from src.security.encryption import Cipher
from test_privacy import csv_bytes, sample_row
from tools import manage

HEADER = "frontera_id,timestamp,consumo_kwh,version_lectura,calidad_lectura\n"
FRONTIER = "CO5770577141"


def consumption(body: str) -> bytes:
    """Construye un CSV pequeño sin datos personales."""
    return (HEADER + body).encode("utf-8")


class BatchTests(unittest.TestCase):
    """Verifica normalización, correcciones e integridad sin tocar las tablas operativas."""

    @classmethod
    def connect(cls, account: str = "superusuario", *, original: bool = False) -> Any:
        """Conecta a la base propia, salvo para crearla o eliminarla explícitamente."""
        user = cls.state[account]
        return psycopg2.connect(host=cls.state["host"], port=cls.state["port"],
                                dbname=cls.state["database"] if original else cls.database,
                                user=user["usuario"], password=user["password"], connect_timeout=5)

    @classmethod
    def setUpClass(cls) -> None:
        """Aplica el SQL real dos veces, sin rotar ninguna contraseña existente."""
        cls.state = manage.load_state()
        cls.database = "bia_s03_test_" + uuid.uuid4().hex
        cls.policy = Classification.load()
        cls.cipher = Cipher(Fernet.generate_key())  # Exclusivamente en memoria para fixtures.
        with closing(cls.connect(original=True)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(cls.database)))
        cls.addClassCleanup(cls.drop_database)
        original = (ROOT / "sql/001_access.sql").read_text(encoding="utf-8")
        original = re.sub(r"SELECT format\('ALTER ROLE.*?\\gexec", "", original, flags=re.DOTALL)
        initial = "\n".join(line for line in original.splitlines() if not line.startswith("\\") and " PASSWORD :'" not in line)
        initial = initial.replace("DATABASE bia_datos", "DATABASE " + cls.database)
        with closing(cls.connect()) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(initial)
                cursor.execute((ROOT / "sql/002_clients.sql").read_text(encoding="utf-8"))
                for _ in range(2):
                    cursor.execute((ROOT / "sql/003_consumptions.sql").read_text(encoding="utf-8"))
        with closing(cls.connect("ingesta")) as connection:
            ingest_bytes(connection, csv_bytes([sample_row("CLI0001")]), cls.policy, cls.cipher)
            load_masters(connection,
                         b"frontera_id,codigo_sic,cliente_id,mercado,operador_red,nivel_tension,fecha_registro,estado\n"
                         + f"{FRONTIER},TEST,CLI0001,Prueba,Prueba,1,2024-01-01,ACTIVA\n".encode(),
                         f"frontera_id,min_kwh,max_kwh\n{FRONTIER},0,100\n".encode(), cls.policy)

    @classmethod
    def drop_database(cls) -> None:
        """Elimina exclusivamente la base aleatoria creada por esta suite."""
        with closing(cls.connect(original=True)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL("DROP DATABASE {}").format(sql.Identifier(cls.database)))

    def query(self, statement: str, parameters: tuple = (), account: str = "superusuario") -> list:
        """Consulta o prepara casos dentro de la base temporal."""
        with closing(self.connect(account)) as connection:
            with connection, connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                return cursor.fetchall() if cursor.description else []

    def load(self, name: str, data: bytes) -> dict[str, int]:
        """Ejecuta persistencia real con los permisos de ingesta."""
        with closing(self.connect("ingesta")) as connection:
            return ingest_file(connection, name, data, self.policy, self.cipher, batch_size=2)

    def snapshot(self) -> dict[str, list]:
        """Captura tablas de negocio y cuarentena, excluyendo auditoría por corrida."""
        tables = ("core.clientes", "core.fronteras", "core.limites_frontera", "core.archivos_ingesta",
                  "core.estado_lectura", "core.fact_consumo_horario", "core.consumos_cuarentena")
        return {table: self.query("SELECT * FROM " + table + " ORDER BY 1,2") for table in tables}

    def test_01_T09_T12_formats_boundaries_and_ties(self) -> None:
        """Prueba formatos, UTC, MWh, límites B4 y desempates dentro y entre archivos."""
        feb = f"frontera_id;timestamp_utc;consumo_kwh;version_lectura;calidad_lectura\n{FRONTIER};2027-02-01T02:00:00Z;12,5;1;OK\n".encode()
        row = normalize(read_csv(feb))[0]
        self.assertEqual(row.timestamp.isoformat(), "2027-01-31T21:00:00-05:00")
        self.assertEqual(str(row.kwh), "12.5")
        march = f"frontera_id,timestamp,kwh,unidad,version_lectura,calidad_lectura\n{FRONTIER},2027-03-01T00:00:00,0.125,MWh,1,OK\n".encode()
        self.assertEqual(normalize(read_csv(march))[0].kwh, 125)
        data = consumption("".join(f"{FRONTIER},2027-01-01T{hour:02}:00:00,{value},1,OK\n"
                                   for hour, value in enumerate(("", "-1", "0", "1000000", "1000000.001"))))
        self.assertEqual([r.reason for r in normalize(read_csv(data))], ["empty", "negative", None, None, "outlier"])
        self.assertEqual(self.load("bounds.csv", data)["rows_loaded"], 2)
        self.load("z-tie.csv", consumption(f"{FRONTIER},2027-01-02T00:00:00,12,1,OK\n{FRONTIER},2027-01-02T00:00:00,13,1,OK\n"))
        self.load("a-tie.csv", consumption(f"{FRONTIER},2027-01-02T00:00:00,10,1,OK\n"))
        self.assertEqual(self.query("SELECT consumo_kwh FROM core.fact_consumo_horario WHERE timestamp=%s", ("2027-01-02T00:00:00-05:00",))[0][0], 13)
        self.load("a-higher.csv", consumption(f"{FRONTIER},2027-01-02T00:00:00,14,2,OK\n"))
        self.assertEqual(self.query("SELECT consumo_kwh FROM core.fact_consumo_horario WHERE timestamp=%s", ("2027-01-02T00:00:00-05:00",))[0][0], 14)
        with closing(self.connect("ingesta")) as connection:
            self.policy.validate_database(connection, tuple(self.policy.tables))
        changed = {table: dict(columns) for table, columns in self.policy.tables.items()}
        changed["core.consumos_cuarentena"]["payload"] = "Interno"
        with self.assertRaises(PrivacyError):
            Classification(changed)

    def test_02_T05_T07_T17_T19_invalid_correction_retry_and_security(self) -> None:
        """Prueba A01 sin resurrección, cuarentena cifrada, permisos y rollback completo."""
        original = consumption(f"{FRONTIER},2027-02-01T00:00:00,100,1,OK\n")
        self.load("base.csv", original)
        correction = consumption(f"{FRONTIER},2027-02-01T00:00:00,-20,2,CORREGIDA\n")
        self.load("correction.csv", correction)
        self.assertEqual(self.query("SELECT count(*) FROM core.fact_consumo_horario WHERE timestamp=%s", ("2027-02-01T00:00:00-05:00",))[0][0], 0)
        self.assertEqual(self.query("SELECT version_lectura,valida FROM core.estado_lectura WHERE timestamp=%s", ("2027-02-01T00:00:00-05:00",))[0], (2, False))
        before = self.snapshot()
        self.load("base.csv", original)
        self.load("correction.csv", correction)
        self.load("older-copy.csv", original)
        self.assertEqual(self.query("SELECT count(*) FROM core.fact_consumo_horario WHERE timestamp=%s", ("2027-02-01T00:00:00-05:00",))[0][0], 0)
        self.assertEqual(before["core.consumos_cuarentena"], self.snapshot()["core.consumos_cuarentena"])
        self.load("recovery.csv", consumption(f"{FRONTIER},2027-02-01T00:00:00,120,3,OK\n"))
        self.assertEqual(self.query("SELECT consumo_kwh FROM core.fact_consumo_horario WHERE timestamp=%s", ("2027-02-01T00:00:00-05:00",))[0][0], 120)
        private = b"person@example.test 3001234567\n\"truncated"
        self.load("private.csv", private)
        stored = self.query("SELECT payload FROM core.consumos_cuarentena WHERE archivo='private.csv'")[0][0]
        self.assertNotIn("person@example.test", stored)
        digest = hashlib.sha256(private).hexdigest()
        context = json.dumps(["private.csv", digest, 0, "invalid_file"], ensure_ascii=True)
        import base64
        self.assertEqual(base64.b64decode(self.cipher.open(stored, context)), private)
        for account, statement in (("analista", "SELECT * FROM core.fact_consumo_horario"),
                                   ("auditor", "SELECT * FROM core.consumos_cuarentena"),
                                   ("ingesta", "TRUNCATE core.fact_consumo_horario"),
                                   ("ingesta", "DELETE FROM audit.runs")):
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                self.query(statement, account=account)
        self.query("CREATE FUNCTION core.s03_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'person@example.test'; END $$; "
                   "CREATE TRIGGER s03_fail BEFORE INSERT ON core.fact_consumo_horario FOR EACH ROW EXECUTE FUNCTION core.s03_fail()")
        snapshot = self.snapshot()
        try:
            with self.assertRaises(PrivacyError) as caught:
                self.load("rollback.csv", consumption(f"{FRONTIER},2027-02-02T00:00:00,1,1,OK\n"))
            self.assertNotIn("person@example.test", str(caught.exception))
            self.assertEqual(snapshot, self.snapshot())
            self.assertEqual(self.query("SELECT result FROM audit.runs ORDER BY recorded_at DESC LIMIT 1")[0][0], "failed")
        finally:
            self.query("DROP TRIGGER s03_fail ON core.fact_consumo_horario; DROP FUNCTION core.s03_fail()")
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / "pipeline.log"
            output = io.StringIO()
            with patch("src.batch.pipeline.Cipher.from_env", side_effect=RuntimeError("person@example.test")), redirect_stdout(output):
                self.assertEqual(main(log_path=log_path), 1)
            self.assertNotIn("person@example.test", output.getvalue() + log_path.read_text())
            json.loads(output.getvalue())

    def test_03_T05_T08_originals_new_month_and_corruption(self) -> None:
        """Carga originales solo en base temporal, repite y añade mes nuevo y archivo truncado."""
        paths = [path for path in (ROOT / "data").rglob("*") if path.is_file()]
        hashes = {path: hashlib.sha256(path.read_bytes()).digest() for path in paths}
        with closing(self.connect("ingesta")) as connection:
            counts = run(connection, ROOT / "data", self.policy, self.cipher)
        self.assertGreater(counts["rows_loaded"], 100000)
        self.assertEqual(counts["files_rejected"], 0)
        self.assertEqual(self.query("SELECT count(*) FROM core.clientes")[0][0], 40)
        snapshot = self.snapshot()
        with closing(self.connect("ingesta")) as connection:
            second = run(connection, ROOT / "data", self.policy, self.cipher)
        self.assertEqual(second["rows_loaded"], 0)
        self.assertEqual(snapshot, self.snapshot())
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "new-month.csv").write_bytes(consumption(f"{FRONTIER},2027-08-01T00:00:00,42,1,OK\n"))
            for path in discover(folder):
                self.load(path.name, path.read_bytes())
            before = self.query("SELECT * FROM core.fact_consumo_horario ORDER BY 1,2")
            # La primera fila alteraría un mes ya cargado si se confirmase antes de detectar el truncamiento.
            (folder / "broken.csv").write_bytes(consumption(f'{FRONTIER},2026-01-01T00:00:00,999,99,OK\n"truncated'))
            for path in discover(folder):
                self.load(path.name, path.read_bytes())
            self.assertEqual(before, self.query("SELECT * FROM core.fact_consumo_horario ORDER BY 1,2"))
            self.assertEqual(self.query("SELECT estado FROM core.archivos_ingesta WHERE archivo='broken.csv'")[0][0], "rejected")
            self.assertEqual(self.query("SELECT consumo_kwh FROM core.fact_consumo_horario WHERE timestamp=%s", ("2027-08-01T00:00:00-05:00",))[0][0], 42)
            # Un contenido distinto bajo el mismo nombre no sustituye silenciosamente el origen inmutable.
            changed = consumption(f"{FRONTIER},2027-08-01T00:00:00,999,99,OK\n")
            self.assertEqual(self.load("new-month.csv", changed)["files_rejected"], 1)
            self.assertEqual(before, self.query("SELECT * FROM core.fact_consumo_horario ORDER BY 1,2"))
            quarantined = self.query("SELECT * FROM core.consumos_cuarentena ORDER BY 1,2,3,4")
            self.load("new-month.csv", changed)
            self.assertEqual(quarantined, self.query("SELECT * FROM core.consumos_cuarentena ORDER BY 1,2,3,4"))
        self.assertEqual(hashes, {path: hashlib.sha256(path.read_bytes()).digest() for path in paths})
