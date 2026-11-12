"""Un escenario de integración con Redpanda real y el productor original sin modificaciones."""
from __future__ import annotations

from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
from time import monotonic
import unittest

from src import ROOT
from src.quality.reports import publish_files
from src.streaming.alerts import AlertEngine
from src.streaming.consumer import read_limits, replay


class StreamingIntegrationTests(unittest.TestCase):
    """Reproduce en el tópico contractual sin administración previa ni borrado de históricos."""

    def test_03_T25_T31_T32_real_producer_twice(self) -> None:
        """Compara Kafka real con un resultado independiente y excluye reproducciones previas."""
        if importlib.util.find_spec("kafka") is None:
            self.skipTest("Integración no verificada: instalar kafka-python con make setup.")
        topic = "mediciones.raw"
        event_file = ROOT / "data/eventos/mediciones_stream.ndjson"
        producer_file = ROOT / "tools/producer.py"
        before = {path: hashlib.sha256(path.read_bytes()).digest() for path in (event_file, producer_file)}
        raw_events = [line for line in event_file.read_bytes().splitlines() if line.strip()]
        expected_engine = AlertEngine(read_limits(ROOT / "data"))
        for raw in raw_events:
            expected_engine.accept(raw)
        expected = expected_engine.finish()
        results = []
        for _ in range(2):
            start = monotonic()
            alerts, consumed = replay(topic=topic)
            self.assertLess(monotonic() - start, 300)
            self.assertEqual(consumed, len(raw_events))
            self.assertEqual(alerts, expected)
            results.append(alerts)
        self.assertEqual(results[0], results[1])
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            publish_files(output, {"alertas.json": json.dumps(results[1])})
            self.assertEqual(json.loads((output / "alertas.json").read_text()), expected)
        self.assertEqual(before, {path: hashlib.sha256(path.read_bytes()).digest() for path in before})
        print("S05 real integration:", json.dumps({"consumed": len(raw_events), "alerts": dict(Counter(item["tipo"] for item in expected))}))
