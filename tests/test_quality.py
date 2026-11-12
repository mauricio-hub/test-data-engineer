"""Tres pruebas críticas S04: contratos, privacidad y recorrido batch repetible."""
from __future__ import annotations

from contextlib import closing, redirect_stdout
import csv
from decimal import Decimal
import hashlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from typing import Any
import unittest
from unittest.mock import patch

import psycopg2

from src import ROOT
from src.batch.load import ingest_billing, report_context
from src.batch.pipeline import main
from src.quality.reports import CSV_HEADER, DQ_KEYS, monthly_csv, publish, quality_report
from src.security import PrivacyError
from src.security.classification import Classification
import test_batch
from tools import manage


def invoice(identifier: str, frontier: str = test_batch.FRONTIER) -> dict:
    """Crea una factura sintética con información personal que nunca debe publicarse."""
    return {"factura_id": identifier, "frontera_id": frontier,
            "cliente": {"nit": "123456789", "email_facturacion": "person@example.test"},
            "consumo_facturado_kwh": 3, "tarifa_cop_kwh": 10, "valor_total_cop": 30,
            "metodo_pago": {"tipo": "test", "cuenta_enmascarada": "person@example.test"},
            "componentes": [{"concepto": "Prueba", "valor_cop_kwh": 4},
                            {"concepto": "person@example.test", "valor_cop_kwh": 6}]}


def billing_bytes(rows: list[dict]) -> bytes:
    """Envuelve facturas en el formato de origen sin usar datos reales de clientes."""
    return json.dumps({"periodo": "2028-01", "emisor": {"nit": "123456789"},
                       "generado_en": "2028-02-01", "facturas": rows}).encode()


class QualityTests(unittest.TestCase):
    """Reutiliza los recursos aislados de S03 sin heredar ni duplicar sus pruebas."""

    connect = classmethod(test_batch.BatchTests.connect.__func__)
    drop_database = classmethod(test_batch.BatchTests.drop_database.__func__)
    query = test_batch.BatchTests.query

    @classmethod
    def setUpClass(cls) -> None:
        """Prepara una base aleatoria propia y aplica SQL 004 dos veces."""
        test_batch.BatchTests.setUpClass.__func__(cls)
        with closing(cls.connect()) as connection:
            with connection, connection.cursor() as cursor:
                for _ in range(2):
                    cursor.execute((ROOT / "sql/004_billing.sql").read_text(encoding="utf-8"))
        cls.policy = Classification.load(include_billing=True)

    def setUp(self) -> None:
        """Aísla facturación entre escenarios, exclusivamente en la base temporal propia."""
        self.query("DELETE FROM core.factura_componentes; DELETE FROM core.facturas; "
                   "DELETE FROM core.facturas_cuarentena; DELETE FROM core.archivos_facturacion")

    def load_invoice(self, name: str, data: bytes) -> dict:
        """Procesa facturación mediante el rol ingesta en la base temporal."""
        with closing(self.connect("ingesta")) as connection:
            return ingest_billing(connection, name, data, self.policy, self.cipher)

    def test_01_T11_T13_T27_T32_contracts_and_calculations(self) -> None:
        """Comprueba resultados pequeños independientes: duplicados, A01, calendario y precisión."""
        frontier = test_batch.FRONTIER
        absent = "CO0000000000"
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / "consumos").mkdir()
            rows = test_batch.consumption(
                f"{frontier},2028-02-01T00:00:00,1.0005,1,OK\n"
                f"{frontier},2028-02-01T00:00:00,1.0005,1,OK\n"
                f"{frontier},2028-02-01T01:00:00,2,1,OK\n"
                f"{frontier},2028-02-01T02:00:00,0,1,OK\n"
                f"{frontier},2028-02-01T03:00:00,,1,OK\n"
                f"{frontier},2028-02-01T04:00:00,1000001,1,OK\n")
            correction = test_batch.consumption(f"{frontier},2028-02-01T01:00:00,-1,2,CORREGIDA\n")
            utc = f"frontera_id;timestamp_utc;consumo_kwh;version_lectura;calidad_lectura\n{frontier};2028-03-01T02:00:00Z;0,5;1;OK\n".encode()
            mwh = f"frontera_id,timestamp,kwh,unidad,version_lectura,calidad_lectura\n{frontier},2028-02-01T05:00:00,0.001,MWh,1,OK\n".encode()
            files = [("a.csv", rows), ("b.csv", correction), ("c.csv", utc), ("d.csv", mwh)]
            for name, data in files:
                (source / "consumos" / name).write_bytes(data)
            context = {"files": [(name, hashlib.sha256(data).hexdigest()) for name, data in files],
                       "monthly": [(frontier, "2028-02", Decimal("2.5005"), 4)],
                       "frontiers": [frontier, absent], "orphans": 2, "pii_clients": 1}
            report = quality_report(source, context)
            self.assertEqual(set(report), set(DQ_KEYS))
            expected = {"filas_leidas": 9, "duplicados_exactos": 1, "duplicados_conflictivos": 1,
                        "registros_negativos": 1, "registros_nulos": 1, "registros_outlier": 1,
                        "registros_mwh_convertidos": 1, "correcciones_tardias_aplicadas": 1,
                        "horas_sin_lectura_valida_total": 1388,
                        "horas_sin_lectura_valida_por_frontera": {frontier: 692, absent: 696},
                        "fronteras_huerfanas_facturacion": 2, "clientes_con_pii_en_texto_libre": 1}
            self.assertEqual(report, expected)
            for key, value in report.items():
                if key != "horas_sin_lectura_valida_por_frontera":
                    self.assertIs(type(value), int)
            exported = monthly_csv(context["monthly"])
            self.assertEqual(exported, ",".join(CSV_HEADER) + f"\n{frontier},2028-02,2.501,4\n")
            out = source / "out"
            publish(out, exported, report, {"timestamp": "test"})
            self.assertEqual(json.loads((out / "dq_report.json").read_text()), expected)
            before = {path.name: path.read_bytes() for path in out.iterdir()}
            with patch("src.quality.reports.os.fsync", side_effect=OSError("person@example.test")):
                with self.assertRaises(OSError):
                    publish(out, "different", report, {})
            self.assertEqual(before, {path.name: path.read_bytes() for path in out.iterdir()})
            (source / "consumos/a.csv").write_bytes(b"changed")
            with self.assertRaises(ValueError):
                quality_report(source, context)

    def test_02_T04_T14_T17_T18_billing_privacy_and_integrity(self) -> None:
        """Verifica huérfanas, componentes, cifrado, clasificación, roles y reintentos."""
        data = billing_bytes([invoice("S04-VALID"), invoice("S04-ORPHAN-1", "unknown"), invoice("S04-ORPHAN-2", "unknown")])
        first = self.load_invoice("s04-test.json", data)
        self.assertEqual((first["rows_read"], first["rows_loaded"], first["rows_rejected"]), (3, 1, 2))
        self.assertEqual(self.query("SELECT count(*) FROM core.factura_componentes")[0][0], 2)
        original = self.query("SELECT * FROM core.facturas")
        quarantined = self.query("SELECT * FROM core.facturas_cuarentena ORDER BY fila")
        self.assertEqual(self.load_invoice("s04-test.json", data)["rows_loaded"], 0)
        self.assertEqual(original, self.query("SELECT * FROM core.facturas"))
        self.assertEqual(quarantined, self.query("SELECT * FROM core.facturas_cuarentena ORDER BY fila"))
        payload = self.query("SELECT payload FROM core.facturas WHERE factura_id='S04-VALID'")[0][0]
        self.assertIn("person@example.test", self.cipher.open(payload, "core.facturas:S04-VALID"))
        for table in ("core.facturas", "core.factura_componentes", "core.facturas_cuarentena"):
            for (encrypted,) in self.query("SELECT payload FROM " + table):
                self.assertTrue(encrypted.startswith("fernet:v1:"))
                self.assertNotIn("person@example.test", encrypted)
        for account, statement in (("analista", "SELECT * FROM core.facturas"),
                                   ("auditor", "SELECT * FROM core.facturas_cuarentena"),
                                   ("ingesta", "DELETE FROM core.facturas")):
            with self.assertRaises(psycopg2.errors.InsufficientPrivilege):
                self.query(statement, account=account)
        self.query("SELECT * FROM analytics.v_consumo_mensual", account="analista")
        self.assertEqual(self.query("SELECT has_table_privilege(current_user,'analytics.v_consumo_mensual','INSERT'),"
                                    "has_table_privilege(current_user,'analytics.v_consumo_mensual','UPDATE'),"
                                    "has_table_privilege(current_user,'analytics.v_consumo_mensual','DELETE')",
                                    account="analista")[0], (False, False, False))
        with self.assertRaises(psycopg2.Error):
            self.query("DELETE FROM analytics.v_consumo_mensual", account="analista")
        changed = {table: dict(columns) for table, columns in self.policy.tables.items()}
        changed["core.facturas"]["payload"] = "Interno"
        with self.assertRaises(PrivacyError):
            Classification(changed)
        self.load_invoice("s04-truncated.json", data[:-5])
        self.assertEqual(original, self.query("SELECT * FROM core.facturas"))

    def test_03_T05_T26_T27_T32_end_to_end_twice_and_publication_failure(self) -> None:
        """Ejecuta el mismo punto de entrada que make run en base aislada y compara salidas."""
        hashes = {path: hashlib.sha256(path.read_bytes()).digest() for path in (ROOT / "data").rglob("*") if path.is_file()}
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            out, log = folder / "out", folder / "logs/pipeline.log"
            events = []
            for _ in range(2):
                capture = io.StringIO()
                with patch("src.batch.pipeline.connect_operational", side_effect=lambda: self.connect("ingesta")), \
                     patch("src.batch.pipeline.Cipher.from_env", return_value=self.cipher), redirect_stdout(capture):
                    self.assertEqual(main(output_path=out, log_path=log), 0)
                events.append(json.loads(capture.getvalue()))
                if len(events) == 1:
                    stable = {name: (out / name).read_bytes() for name in ("consumo_mensual.csv", "dq_report.json")}
            self.assertEqual(stable, {name: (out / name).read_bytes() for name in stable})
            self.assertEqual(events[0]["filas_leidas"], 115512)
            self.assertEqual(events[1]["filas_leidas"], 0)
            self.assertEqual(events[1]["filas_cargadas"], 0)
            self.assertEqual(events[1]["filas_rechazadas_por_motivo"], {})
            report = json.loads((out / "dq_report.json").read_text())
            self.assertEqual(set(report), set(DQ_KEYS))
            self.assertEqual(report["filas_leidas"], 115340)
            self.assertEqual(report["duplicados_exactos"], 180)
            self.assertEqual(report["duplicados_conflictivos"], 420)
            self.assertEqual(report["correcciones_tardias_aplicadas"], 300)
            self.assertEqual(report["fronteras_huerfanas_facturacion"], 12)
            self.assertEqual(report["horas_sin_lectura_valida_total"], 655)
            self.assertEqual(report["registros_mwh_convertidos"], 400)
            self.assertEqual(report["clientes_con_pii_en_texto_libre"], 25)
            rows = list(csv.DictReader(io.StringIO((out / "consumo_mensual.csv").read_text())))
            self.assertEqual(len(rows), 160)
            self.assertEqual(sum(int(row["horas_con_dato"]) for row in rows), 114545)
            with closing(self.connect("analista")) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT sum(horas_con_dato) FROM analytics.v_consumo_mensual")
                    self.assertEqual(cursor.fetchone()[0], 114545)
            for path in out.iterdir():
                self.assertNotIn("person@example.test", path.read_text())
            for line in log.read_text().splitlines():
                json.loads(line)
            snapshot = {path.name: path.read_bytes() for path in out.iterdir()}
            capture = io.StringIO()
            with patch("src.batch.pipeline.connect_operational", side_effect=lambda: self.connect("ingesta")), \
                 patch("src.batch.pipeline.Cipher.from_env", return_value=self.cipher), \
                 patch("src.quality.reports.os.replace", side_effect=OSError("person@example.test")), redirect_stdout(capture):
                self.assertEqual(main(output_path=out, log_path=log), 1)
            self.assertEqual(snapshot, {path.name: path.read_bytes() for path in out.iterdir()})
            self.assertNotIn("person@example.test", capture.getvalue() + log.read_text())
            self.assertEqual(self.query("SELECT result FROM audit.runs ORDER BY recorded_at DESC LIMIT 1")[0][0], "failed")
            # Salidas borradas por el evaluador: regenerar sin tocar la base ni depender de archivos previos.
            regenerated = folder / "regenerated/out"
            with patch("src.batch.pipeline.connect_operational", side_effect=lambda: self.connect("ingesta")), \
                 patch("src.batch.pipeline.Cipher.from_env", return_value=self.cipher), redirect_stdout(io.StringIO()):
                self.assertEqual(main(output_path=regenerated, log_path=log), 0)
            self.assertEqual(stable, {name: (regenerated / name).read_bytes() for name in stable})
            with patch("sys.argv", ["manage.py", "run"]), \
                 patch("tools.manage.subprocess.run", return_value=SimpleNamespace(returncode=0)) as command:
                self.assertEqual(manage.main(), 0)
                self.assertEqual(command.call_args.args[0][-2:], ["-m", "src.batch.pipeline"])
                self.assertEqual(command.call_args.kwargs["timeout"], 900)
                command.return_value.returncode = 1
                self.assertEqual(manage.main(), 1)
            print("S04 isolated first/second:", json.dumps(events))
            print("S04 isolated quality:", json.dumps(report))
        self.assertEqual(hashes, {path: hashlib.sha256(path.read_bytes()).digest() for path in hashes})
