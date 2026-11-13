"""Dos escenarios críticos de streaming sin depender de Kafka: reglas y fallos seguros."""
from __future__ import annotations

from contextlib import redirect_stdout
from datetime import timedelta
from decimal import Decimal
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace, ModuleType
import unittest
from unittest.mock import MagicMock, patch, create_autospec, call

from src.streaming.alerts import AlertEngine, DAY_START, InvalidEvent
from src.streaming.consumer import StreamError, consume_range, main, produce, replay
from tools import manage

FRONTIER = "CO0000000001"


def event(index: int, kwh: int = 100) -> bytes:
    """Construye una medición sintética con un objeto privado que debe ignorarse."""
    return json.dumps({"frontera_id": FRONTIER, "ts_medicion": (DAY_START + timedelta(minutes=index * 15)).isoformat(),
                       "kwh": kwh, "medidor": {"texto": "person@example.test"}}).encode()


class StreamingTests(unittest.TestCase):
    """Comprueba reglas exactas, cierre de recursos y errores que no filtran contenido."""

    def test_01_T22_T24_T32_rules_boundaries_recovery_and_late_arrival(self) -> None:
        """Verifica tercero ausente, recuperación, extremos del día y máximo temporal persistente."""
        engine = AlertEngine({FRONTIER: Decimal(100)})
        gaps = {0, 1, 2, 8, 9, 10, 11, 93, 94, 95}
        for index in range(96):
            if index not in gaps:
                engine.accept(event(index))
        missing = [item["ts"] for item in engine.finish() if item["tipo"] == "FRONTERA_SIN_REPORTE"]
        self.assertEqual(missing, [(DAY_START + timedelta(minutes=index * 15)).isoformat() for index in (2, 10, 95)])
        late = AlertEngine({FRONTIER: Decimal(100)})
        for index in range(96):
            if index not in (0, 1, 2):
                late.accept(event(index))
        late.accept(event(1))  # Su presencia final divide la racha inicial: ya no hay tres ausencias.
        late.accept(event(50, 101))
        late.accept(event(50, 101))
        late.accept(event(94))  # Sigue siendo retroactiva tras recibir la lectura del intervalo 50.
        late.accept(event(95, -1))  # B4 no se extiende a streaming; no hay regla por mínimo.
        result = late.finish()
        self.assertFalse(any(item["tipo"] == "FRONTERA_SIN_REPORTE" for item in result))
        self.assertEqual(sum(item["tipo"] == "CONSUMO_FUERA_DE_BANDA" for item in result), 1)
        self.assertEqual(sum(item["tipo"] == "LECTURA_RETROACTIVA" for item in result), 3)
        self.assertEqual(len(result), len({(item["tipo"], item["frontera_id"], item["ts"]) for item in result}))
        self.assertEqual(late.latest[FRONTIER], DAY_START + timedelta(minutes=95 * 15))
        self.assertEqual(result, late.finish())
        self.assertNotIn("person@example.test", json.dumps(result))
        self.assertTrue(all(set(item) == {"tipo", "frontera_id", "ts"} and item["ts"].endswith("-05:00") for item in result))
        never = AlertEngine({FRONTIER: Decimal(100)})
        self.assertEqual(never.finish(), [{"tipo": "FRONTERA_SIN_REPORTE", "frontera_id": FRONTIER,
                                          "ts": (DAY_START + timedelta(minutes=30)).isoformat()}])
        utc = json.loads(event(0, 101))
        utc["ts_medicion"] = "2026-06-01T05:00:00Z"
        never.accept(json.dumps(utc).encode())
        self.assertIn(("CONSUMO_FUERA_DE_BANDA", FRONTIER, DAY_START), never.alerts)
        for bad in (b"not-json", b'{}', event(96), event(-1), b'{"kwh": "person@example.test"}'):
            with self.assertRaises(InvalidEvent) as caught:
                AlertEngine({FRONTIER: Decimal(100)}).accept(bad)
            self.assertNotIn("person@example.test", str(caught.exception))

    def test_02_T25_T26_T31_failures_offsets_timeout_and_publication(self) -> None:
        """Comprueba rango, fallo del productor, timeout y retorno seguro sin alterar la salida."""
        consumer = MagicMock()
        record = SimpleNamespace(offset=7, partition=3, value=event(0))
        consumer.poll.return_value = {"part": [SimpleNamespace(offset=6, partition=3, value=b"old"), record,
                                                SimpleNamespace(offset=8, partition=3, value=b"later")]}
        engine = AlertEngine({FRONTIER: Decimal(100)})
        self.assertEqual(consume_range(consumer, {"part": 7}, {"part": 8}, engine, float("inf")), 1)
        consumer.seek.assert_called_once_with("part", 7)
        consumer.commit.assert_not_called()
        record.value = b'person@example.test'
        with self.assertRaises(StreamError) as caught:
            consume_range(consumer, {"part": 7}, {"part": 8}, engine, float("inf"))
        self.assertEqual((caught.exception.reason, caught.exception.partition, caught.exception.offset), ("invalid_event", 3, 7))
        with self.assertRaises(StreamError) as caught:
            consume_range(consumer, {"part": 7}, {"part": 8}, engine, 0)
        self.assertEqual(caught.exception.reason, "deadline_exceeded")
        with self.assertRaises(StreamError):
            consume_range(consumer, {"part": 8}, {"part": 7}, engine, float("inf"))
        record.offset, record.value = 8, event(0)
        consumer.poll.return_value = {"part": [record]}
        with self.assertRaises(StreamError) as caught:
            consume_range(consumer, {"part": 7}, {"part": 9}, engine, float("inf"))
        self.assertEqual(caught.exception.reason, "incomplete_replay")
        with patch("src.streaming.consumer.subprocess.run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(StreamError) as caught:
                produce(Path("synthetic"), "test", "localhost:9092", float("inf"))
            self.assertEqual(caught.exception.reason, "producer_failed")
        with patch("src.streaming.consumer.subprocess.run", side_effect=subprocess.TimeoutExpired("producer", 1)):
            with self.assertRaises(StreamError) as caught:
                produce(Path("synthetic"), "test", "localhost:9092", float("inf"))
            self.assertEqual(caught.exception.reason, "deadline_exceeded")
        kafka, admin_module, errors = ModuleType("kafka"), ModuleType("kafka.admin"), ModuleType("kafka.errors")
        from kafka import KafkaConsumer as ConsumerAPI
        # Usar la firma real impide que un mock acepte timeout_ms en end_offsets por error.
        fake_admin, fake_consumer = MagicMock(), create_autospec(ConsumerAPI, instance=True)
        fake_admin.list_topics.return_value = ["test"]
        fake_consumer.partitions_for_topic.return_value = {0}
        fake_consumer.end_offsets.return_value = {("test", 0): 0}
        kafka.KafkaConsumer = MagicMock(return_value=fake_consumer)
        kafka.TopicPartition = MagicMock(side_effect=lambda topic, partition: (topic, partition))
        admin_module.KafkaAdminClient = MagicMock(return_value=fake_admin)
        admin_module.NewTopic = MagicMock()
        errors.TopicAlreadyExistsError = RuntimeError
        with patch.dict("sys.modules", {"kafka": kafka, "kafka.admin": admin_module, "kafka.errors": errors}), \
             patch("src.streaming.consumer.produce", side_effect=StreamError("producer_failed")):
            with self.assertRaises(StreamError) as replay_error:
                replay(topic="test")
        self.assertEqual(replay_error.exception.stage, "producer")
        fake_consumer.close.assert_called_once_with(autocommit=False, timeout_ms=3000)
        admin_module.KafkaAdminClient.assert_not_called()
        fake_admin.close.assert_not_called()
        # Regresión: un administrador que falla no debe impedir consumir un tópico existente.
        from src import ROOT
        expected = sum(bool(line.strip()) for line in (ROOT / "data/eventos/mediciones_stream.ndjson").read_bytes().splitlines())
        admin_factory = admin_module.KafkaAdminClient
        admin_factory.side_effect = RuntimeError("NodeNotReadyError: 0")
        fake_consumer.reset_mock()
        fake_consumer.end_offsets.side_effect = [{("test", 0): 0}, {("test", 0): expected}]
        with patch.dict("sys.modules", {"kafka": kafka, "kafka.admin": admin_module, "kafka.errors": errors}), \
             patch("src.streaming.consumer.produce") as publisher, \
             patch("src.streaming.consumer.consume_range", return_value=expected):
            _, consumed = replay(topic="test")
        self.assertEqual(consumed, expected)
        self.assertEqual(fake_consumer.end_offsets.call_args_list,
                         [call([("test", 0)]), call([("test", 0)])])
        publisher.assert_called_once()
        admin_factory.assert_not_called()
        fake_consumer.close.assert_called_once_with(autocommit=False, timeout_ms=3000)
        # El tópico ausente sigue creándose; la propagación se consulta con el consumidor.
        admin_factory.side_effect = None
        fake_consumer.reset_mock()
        fake_consumer.partitions_for_topic.side_effect = [None, {0}, {0}]
        fake_consumer.topics.return_value = set()
        fake_consumer.end_offsets.side_effect = [{("test", 0): 0}, {("test", 0): expected}]
        with patch.dict("sys.modules", {"kafka": kafka, "kafka.admin": admin_module, "kafka.errors": errors}), \
             patch("src.streaming.consumer.produce"), \
             patch("src.streaming.consumer.consume_range", return_value=expected):
            self.assertEqual(replay(topic="test")[1], expected)
        admin_factory.assert_called_once()
        fake_admin.create_topics.assert_called_once()
        fake_admin.close.assert_called_once()
        # El fallo administrativo queda localizado y cierra el consumidor ya abierto.
        admin_factory.side_effect = RuntimeError("NodeNotReadyError: 0")
        fake_consumer.reset_mock()
        fake_consumer.partitions_for_topic.side_effect = None
        fake_consumer.partitions_for_topic.return_value = None
        with patch.dict("sys.modules", {"kafka": kafka, "kafka.admin": admin_module, "kafka.errors": errors}):
            with self.assertRaises(StreamError) as replay_error:
                replay(topic="test")
        self.assertEqual(replay_error.exception.stage, "topic_creation")
        fake_consumer.close.assert_called_once_with(autocommit=False, timeout_ms=3000)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder / "alertas.json").write_text("[]\n", encoding="utf-8")
            connection = MagicMock()
            output = io.StringIO()
            with patch("src.streaming.consumer.connect_operational", return_value=connection), \
                 patch("src.streaming.consumer.replay", side_effect=StreamError("invalid_event", consumed=1, partition=3, offset=7)), \
                 redirect_stdout(output):
                self.assertEqual(main(output=folder, log_path=folder / "pipeline.log"), 1)
            self.assertEqual((folder / "alertas.json").read_text(), "[]\n")
            self.assertNotIn("person@example.test", output.getvalue() + (folder / "pipeline.log").read_text())
            self.assertEqual(json.loads(output.getvalue())["offset"], 7)
            connection.close.assert_called_once()
            with patch("src.streaming.consumer.connect_operational", return_value=MagicMock()), \
                 patch("src.streaming.consumer.replay", return_value=([], 1)), \
                 patch("src.quality.reports.os.replace", side_effect=OSError("person@example.test")), redirect_stdout(io.StringIO()):
                self.assertEqual(main(output=folder, log_path=folder / "pipeline.log"), 1)
            self.assertEqual((folder / "alertas.json").read_text(), "[]\n")
        with patch("sys.argv", ["manage.py", "stream"]), \
             patch("tools.manage.subprocess.run", return_value=SimpleNamespace(returncode=0)) as command:
            self.assertEqual(manage.main(), 0)
            self.assertEqual(command.call_args.args[0][-2:], ["-m", "src.streaming.consumer"])
            self.assertEqual(command.call_args.kwargs["timeout"], 280)
            command.return_value.returncode = 1
            self.assertEqual(manage.main(), 1)

    def test_configurable_connections_preserve_official_defaults_and_audit(self) -> None:
        """Usa conexiones simuladas: conserva defaults y solo audita en la conexión elegida."""
        alerts = [{"tipo": "CONSUMO_FUERA_DE_BANDA", "frontera_id": FRONTIER,
                   "ts": DAY_START.isoformat()}]
        with tempfile.TemporaryDirectory() as directory:
            for mode in ("official", "demo"):
                folder = Path(directory) / mode
                connection = MagicMock()
                factory = MagicMock(return_value=connection)
                with self.subTest(mode=mode), \
                     patch("src.streaming.consumer.connect_operational", return_value=connection) as default, \
                     patch("src.streaming.consumer.replay", return_value=(alerts, 1)) as replay_call, \
                     redirect_stdout(io.StringIO()):
                    kwargs = {} if mode == "official" else {
                        "connection_factory": factory, "bootstrap": "127.0.0.1:19092"}
                    self.assertEqual(main(output=folder, log_path=folder / "pipeline.log", **kwargs), 0)
                    first = (folder / "alertas.json").read_bytes()
                    self.assertEqual(main(output=folder, log_path=folder / "pipeline.log", **kwargs), 0)
                    self.assertEqual(first, (folder / "alertas.json").read_bytes())
                    if mode == "official":
                        self.assertEqual(replay_call.call_args_list, [call(), call()])
                        self.assertEqual(default.call_count, 2)
                        factory.assert_not_called()
                    else:
                        self.assertEqual(replay_call.call_args_list,
                                         [call(bootstrap="127.0.0.1:19092"), call(bootstrap="127.0.0.1:19092")])
                        default.assert_not_called()
                        self.assertEqual(factory.call_count, 2)
                    statements = connection.cursor.return_value.__enter__.return_value.execute.call_args_list
                    self.assertEqual(len(statements), 2)
                    self.assertTrue(all(c.args[0].startswith("SELECT audit.record_run(") for c in statements))
                    self.assertEqual(connection.commit.call_count, 2)
                    self.assertEqual(connection.close.call_count, 2)
