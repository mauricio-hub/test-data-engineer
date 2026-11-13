"""Comprueba barreras del entorno de ensayo y su ciclo real opcional."""
from __future__ import annotations

from contextlib import closing, nullcontext, redirect_stdout
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src import ROOT
from src.security import PrivacyError
from tools import demo


class DemoTests(unittest.TestCase):
    """Verifica aislamiento y reinicio sin ejecutar Docker ni tocar datos reales."""

    def test_stream_requires_existing_state_without_writing_secrets(self) -> None:
        """Streaming no crea estado ni reescribe credenciales cuando lee una demo existente."""
        with tempfile.TemporaryDirectory() as directory, patch.object(demo, "HOME", Path(directory)), \
             patch.object(demo, "private_write") as write, patch.object(demo, "command") as command:
            with self.assertRaises(demo.DemoError):
                demo.state(existing_only=True)
            value = {name: {"password": str(index) * 64} for index, name in enumerate(
                ("superusuario", "ingesta", "analista", "auditor"), 1)}
            value["marker"] = "a" * 64
            (Path(directory) / "state.json").write_text(json.dumps(value))
            (Path(directory) / "postgres_password").write_text(value["superusuario"]["password"])
            self.assertEqual(demo.state(existing_only=True), value)
            write.assert_not_called()
            command.assert_not_called()

    def test_stream_routes_to_demo_and_never_initializes_or_resets(self) -> None:
        """El adaptador delega en el consumidor original, con conexión y salidas aisladas."""
        for result in (0, 1):
            value = {"fixture": True}
            admin, operational = MagicMock(), MagicMock()

            def stream(**kwargs: object) -> int:
                """Inspecciona la configuración sin publicar eventos ni abrir conexiones reales."""
                self.assertEqual(kwargs["bootstrap"], "127.0.0.1:19092")
                self.assertEqual(kwargs["output"], demo.HOME / "out")
                self.assertEqual(kwargs["log_path"], demo.HOME / "out/pipeline.log")
                self.assertIs(kwargs["connection_factory"](), operational)
                return result

            with self.subTest(result=result), patch("sys.argv", ["demo", "stream"]), \
                 patch.object(demo, "exclusive", return_value=nullcontext()), \
                 patch.object(demo, "state", return_value=value) as state, \
                 patch.object(demo, "connect", side_effect=[admin, operational]) as connect, \
                 patch.object(demo, "inspect_demo") as identity, \
                 patch.object(demo, "verify_database") as database_identity, \
                 patch.object(demo, "prepare_broker") as prepare_broker, \
                 patch.object(demo, "prepare") as prepare, patch.object(demo, "reset") as reset, \
                 patch.object(demo, "private_write") as write, \
                 patch("src.security.keys.initialize_key") as key, \
                 patch("src.streaming.consumer.main", side_effect=stream) as consumer:
                self.assertEqual(demo.main(), result)
                state.assert_called_once_with(existing_only=True)
                self.assertEqual(connect.call_args_list, [unittest.mock.call(value, admin=True), unittest.mock.call(value)])
                identity.assert_called_once()
                database_identity.assert_called_once()
                prepare_broker.assert_called_once()
                consumer.assert_called_once()
                prepare.assert_not_called()
                reset.assert_not_called()
                key.assert_not_called()
                write.assert_not_called()

    def test_stream_identity_failure_blocks_broker_and_consumer(self) -> None:
        """Un PostgreSQL no identificado impide arrancar el broker o auditar en otra base."""
        with patch("sys.argv", ["demo", "stream"]), \
             patch.object(demo, "exclusive", return_value=nullcontext()), \
             patch.object(demo, "state", return_value={}), \
             patch.object(demo, "inspect_demo", side_effect=demo.DemoError("Identidad incorrecta")), \
             patch.object(demo, "connect") as connect, patch.object(demo, "prepare_broker") as broker, \
             patch("src.streaming.consumer.main") as stream, redirect_stdout(io.StringIO()) as output:
            self.assertEqual(demo.main(), 1)
            self.assertEqual(json.loads(output.getvalue())["stage"], "container_identity")
            connect.assert_not_called()
            broker.assert_not_called()
            stream.assert_not_called()

    def test_broker_start_targets_only_redpanda_and_preserves_postgres_config(self) -> None:
        """Genera Compose temporal y verifica que no se invoque SQL ni arranque PostgreSQL."""
        initial = {"services": {"postgres": {"image": "fixture", "ports": ["127.0.0.1:55433:5432"]}},
                   "volumes": {"pgdata": {"name": demo.VOLUME}},
                   "secrets": {"postgres_password": {"file": "postgres_password"}}}
        with tempfile.TemporaryDirectory() as directory, patch.object(demo, "HOME", Path(directory)), \
             patch.object(demo, "inspect_demo") as postgres, patch.object(demo, "inspect_broker") as broker, \
             patch.object(demo, "command") as command, patch.object(demo, "connect") as connect:
            path = Path(directory) / "compose.json"
            path.write_text(json.dumps(initial))
            demo.prepare_broker()
            after = json.loads(path.read_text())
            self.assertEqual(after["services"]["postgres"], initial["services"]["postgres"])
            self.assertEqual(after["volumes"]["pgdata"], initial["volumes"]["pgdata"])
            self.assertEqual(after["secrets"], initial["secrets"])
            service = after["services"]["redpanda"]
            self.assertEqual(service["ports"], ["127.0.0.1:19092:9092"])
            self.assertIn("--advertise-kafka-addr=internal://redpanda:29092,external://127.0.0.1:19092", service["command"])
            self.assertEqual(after["volumes"]["rpdata"], {"name": "bia-demo_rpdata"})
            command.assert_called_once_with(demo.compose("up", "-d", "--no-deps", "--wait", "--wait-timeout", "120", "redpanda"))
            self.assertEqual(postgres.call_count, 2)
            self.assertEqual(broker.call_args_list, [unittest.mock.call(required=False), unittest.mock.call()])
            connect.assert_not_called()

    def test_broker_identity_rejects_main_ports_volumes_and_project(self) -> None:
        """Valida recursos reales mediante respuestas simuladas, sin consultar Docker."""
        volume = [{"Labels": {"com.docker.compose.project": "bia-demo", "com.docker.compose.volume": "rpdata"}}]
        info = {"Config": {"Labels": {"com.docker.compose.project": "bia-demo", "com.docker.compose.service": "redpanda"}},
                "Mounts": [{"Destination": "/var/lib/redpanda/data", "Type": "volume", "Name": demo.BROKER_VOLUME}],
                "HostConfig": {"PortBindings": {"9092/tcp": [{"HostIp": "127.0.0.1", "HostPort": "19092"}]}},
                "State": {"Running": True},
                "NetworkSettings": {"Ports": {"9092/tcp": [{"HostIp": "127.0.0.1", "HostPort": "19092"}]}}}
        for target in ("valid", "project", "port", "volume", "stopped"):
            changed = json.loads(json.dumps(info))
            if target == "project":
                changed["Config"]["Labels"]["com.docker.compose.project"] = "bia-evaluation"
            elif target == "port":
                changed["HostConfig"]["PortBindings"]["9092/tcp"][0]["HostPort"] = "9092"
            elif target == "volume":
                changed["Mounts"][0]["Name"] = "bia-evaluation_rpdata"
            elif target == "stopped":
                changed["State"]["Running"] = False
            with self.subTest(target=target), patch.object(demo, "command", side_effect=[
                    demo.BROKER_VOLUME, json.dumps(volume), "broker-id", json.dumps([changed])]):
                if target == "valid":
                    demo.inspect_broker()
                else:
                    with self.assertRaises(demo.DemoError):
                        demo.inspect_broker()
        with patch.object(demo, "command", side_effect=[demo.BROKER_VOLUME, '[{"Labels": {}}]']):
            with self.assertRaises(demo.DemoError):
                demo.inspect_broker(required=False)

    def test_privacy_error_reports_safe_code_and_initialization_stage(self) -> None:
        """Simula fallos de llave antes de cualquier preparación o reinicio real."""
        for code in ("key_initialization_blocked", "key_missing", "key_invalid"):
            with self.subTest(code=code), patch("sys.argv", ["demo", "reset", "--confirm", "bia-demo"]), \
                 patch.object(demo, "exclusive", return_value=nullcontext()), \
                 patch("src.security.keys.initialize_key", side_effect=PrivacyError(code)) as initialize, \
                 patch.object(demo, "state") as state, patch.object(demo, "prepare") as prepare, \
                 patch.object(demo, "reset") as reset, redirect_stdout(io.StringIO()) as output:
                self.assertEqual(demo.main(), 1)
                self.assertEqual(json.loads(output.getvalue()), {
                    "event": "demo_failed", "reason": code, "stage": "key_initialization"})
                initialize.assert_called_once_with(ROOT, scope="demo")
                state.assert_not_called()
                prepare.assert_not_called()
                reset.assert_not_called()

    def test_unexpected_errors_hide_details_and_report_the_stage(self) -> None:
        """No publica excepciones crudas de permisos, rutas o JSON del estado local."""
        sensitive = "password=synthetic-secret person@example.test C:/private/key"
        for error in (PermissionError(sensitive), ValueError(sensitive)):
            with self.subTest(error=type(error).__name__), \
                 patch("sys.argv", ["demo", "reset", "--confirm", "bia-demo"]), \
                 patch.object(demo, "exclusive", return_value=nullcontext()), \
                 patch("src.security.keys.initialize_key") as initialize, \
                 patch.object(demo, "state", side_effect=error), \
                 patch.object(demo, "prepare") as prepare, patch.object(demo, "reset") as reset, \
                 redirect_stdout(io.StringIO()) as output:
                self.assertEqual(demo.main(), 1)
                event = json.loads(output.getvalue())
                self.assertEqual(event["stage"], "local_state")
                self.assertEqual(event["reason"], "Operación bloqueada o fallida; no se muestran detalles sensibles.")
                self.assertNotIn(sensitive, output.getvalue())
                initialize.assert_called_once()
                prepare.assert_not_called()
                reset.assert_not_called()

    def test_inventory_matches_sql_and_preserves_audit(self) -> None:
        """El inventario debe contener todas las tablas core y excluir auditoría."""
        names = set()
        for path in (ROOT / "sql").glob("*.sql"):
            names.update(re.findall(r"CREATE TABLE IF NOT EXISTS core\.(\w+)", path.read_text()))
        self.assertEqual(set(demo.TABLES), names)
        self.assertEqual(len(demo.TABLES), 12)
        cursor = MagicMock()
        cursor.fetchall.side_effect = [[("marker",)], [(name,) for name in names]]
        cursor.fetchone.return_value = (0,)
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor
        demo.reset(connection, {"marker": "marker"})
        statements = [call.args[0] for call in cursor.execute.call_args_list]
        truncate = next(s for s in statements if s.startswith("TRUNCATE"))
        self.assertNotIn("CASCADE", truncate)
        self.assertNotIn("audit.", truncate)
        self.assertEqual(set(truncate.removeprefix("TRUNCATE TABLE ").split(", ")),
                         {"core." + name for name in names})

    def test_rejects_primary_container_port_and_volume(self) -> None:
        """Cada prueba de identidad bloquea por separado un destino incorrecto."""
        info = {"Config": {"Labels": {"com.docker.compose.project": "bia-demo",
                                       "com.docker.compose.service": "postgres"}},
                "Mounts": [{"Destination": "/var/lib/postgresql/data", "Type": "volume",
                            "Name": "bia-demo_pgdata"}],
                "NetworkSettings": {"Ports": {"5432/tcp": [
                    {"HostIp": "127.0.0.1", "HostPort": "55433"}]}}}
        demo.verify_container(info)
        for target in ("project", "port", "volume"):
            changed = json.loads(json.dumps(info))
            if target == "project":
                changed["Config"]["Labels"]["com.docker.compose.project"] = "bia-evaluation"
            elif target == "port":
                changed["NetworkSettings"]["Ports"]["5432/tcp"][0]["HostPort"] = "55432"
            else:
                changed["Mounts"][0]["Name"] = "bia-evaluation_pgdata"
            with self.subTest(target=target), self.assertRaises(demo.DemoError):
                demo.verify_container(changed)

    def test_reset_requires_confirmation_marker_and_inventory(self) -> None:
        """Sin confirmación, marcador o inventario exacto no se alcanza TRUNCATE."""
        with patch("sys.argv", ["demo", "reset"]), patch.object(demo, "state") as state:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(demo.main(), 1)
            state.assert_not_called()
        for rows in (([("wrong",)],), ([("marker",)], [("clientes",)])):
            cursor = MagicMock()
            cursor.fetchall.side_effect = rows
            connection = MagicMock()
            connection.cursor.return_value.__enter__.return_value = cursor
            with self.assertRaises(demo.DemoError):
                demo.reset(connection, {"marker": "marker"})
            self.assertFalse(any(c.args[0].startswith("TRUNCATE")
                                 for c in cursor.execute.call_args_list))

    def test_existing_foreign_volume_blocks_start(self) -> None:
        """Un volumen ajeno se rechaza antes de arrancar el contenedor."""
        with patch.object(demo, "command", side_effect=[demo.VOLUME, '[{"Labels": {}}]']) as call:
            with self.assertRaises(demo.DemoError):
                demo.prepare({})
            self.assertEqual(call.call_count, 2)

    def test_local_state_is_separate_and_operations_are_exclusive(self) -> None:
        """Credenciales se conservan y el bloqueo impide comandos simultáneos."""
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "demo"
            with patch.object(demo, "HOME", home), patch.object(demo, "command", return_value=""):
                with demo.exclusive():
                    first = demo.state()
                    self.assertEqual(first, demo.state())
                    with self.assertRaises(demo.DemoError):
                        with demo.exclusive():
                            self.fail("No debe adquirir otro bloqueo")
                self.assertFalse((home / "operation.lock").exists())
                self.assertFalse((Path(temporary) / "ingesta.json").exists())
                self.assertFalse((Path(temporary) / "entrega.yaml").exists())


@unittest.skipUnless(os.environ.get("BIA_DEMO_INTEGRATION") == "1",
                     "Requiere autorización explícita BIA_DEMO_INTEGRATION=1 y Docker")
class DemoIntegrationTests(unittest.TestCase):
    """Ensaya reinicio, carga y repetición real únicamente sobre bia-demo."""

    def test_reset_load_idempotence(self) -> None:
        """Conserva auditoría y principales archivos locales; compara negocio y salidas."""
        # La preparación demo puede crear su propia llave solo si no existe almacenamiento previo.
        protected = [ROOT / "entrega.yaml", ROOT / ".local/ingesta.json",
                     ROOT / ".local/evaluation.json", ROOT / "out/consumo_mensual.csv",
                     ROOT / "out/dq_report.json"]
        original = {p: p.read_bytes() if p.exists() else None for p in protected}

        def invoke(action: str) -> None:
            """Ejecuta la herramienta sin imprimir métricas durante la prueba."""
            with patch("sys.argv", ["demo", action, "--confirm", "bia-demo"]):
                with redirect_stdout(io.StringIO()):
                    self.assertEqual(demo.main(), 0)

        def snapshot() -> tuple:
            """Compara todo el negocio, incluidas precedencias y cuarentenas cifradas."""
            with closing(demo.connect(value, admin=True)) as connection:
                with connection.cursor() as cursor:
                    tables = []
                    for name in demo.TABLES:
                        cursor.execute("SELECT row_to_json(t)::text FROM core." + name + " t ORDER BY 1")
                        tables.append(cursor.fetchall())
                    cursor.execute("SELECT count(*) FROM audit.runs")
                    audit = cursor.fetchone()[0]
            hashes = [hashlib.sha256((demo.HOME / "out" / name).read_bytes()).hexdigest()
                      for name in ("consumo_mensual.csv", "dq_report.json")]
            return tables, hashes, audit

        invoke("reset")
        value = demo.state()
        with closing(demo.connect(value, admin=True)) as connection:
            with connection.cursor() as cursor:
                for name in demo.TABLES:
                    cursor.execute("SELECT count(*) FROM core." + name)
                    self.assertEqual(cursor.fetchone()[0], 0)
                cursor.execute("SELECT count(*) FROM audit.runs")
                before = cursor.fetchone()[0]
        invoke("run")
        first = snapshot()
        for table in ("clientes", "fronteras", "fact_consumo_horario", "facturas"):
            self.assertTrue(first[0][demo.TABLES.index(table)])
        invoke("run")
        second = snapshot()
        self.assertEqual(first[:2], second[:2])
        self.assertGreater(first[2], before)
        self.assertGreater(second[2], first[2])
        invoke("reset")
        with closing(demo.connect(value, admin=True)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT count(*) FROM audit.runs")
                self.assertEqual(cursor.fetchone()[0], second[2])
                for name in demo.TABLES:
                    cursor.execute("SELECT count(*) FROM core." + name)
                    self.assertEqual(cursor.fetchone()[0], 0)
        self.assertEqual(original, {p: p.read_bytes() if p.exists() else None for p in protected})
