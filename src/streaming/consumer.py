"""Reproduce con el productor original y consume un rango finito de Kafka sin publicar PII."""
from __future__ import annotations

from collections import Counter
from contextlib import closing
from decimal import Decimal
import json
import logging
from pathlib import Path
import subprocess
import sys
from time import monotonic, sleep
from typing import Any, Callable
import uuid

from src import ROOT
from src.batch.extract import read_csv
from src.client_service import connect_operational
from src.observability import record_run, stream_event
from src.quality.reports import publish_files
from src.security import PrivacyError
from src.streaming.alerts import AlertEngine, InvalidEvent, TYPES

REASONS = {"invalid_event", "producer_failed", "incomplete_replay", "deadline_exceeded", "broker_error",
           "source_error", "publication_error", "database_error", "internal_error", "dependency_missing"}
STAGES = {"consumer_connection", "topic_metadata", "topic_creation", "start_offsets", "producer",
          "end_offsets", "consume", "alerts"}


class StreamError(Exception):
    """Comunica códigos cerrados y posiciones Kafka; nunca conserva mensajes crudos."""

    def __init__(self, reason: str, *, consumed: int = 0, partition: int | None = None,
                 offset: int | None = None, stage: str | None = None) -> None:
        """Acepta solo motivos internos y metadatos técnicos de la operación."""
        self.reason = reason if reason in REASONS else "internal_error"
        self.consumed, self.partition, self.offset = consumed, partition, offset
        self.stage = stage if stage in STAGES else None
        super().__init__("No se pudo completar la reproducción de streaming.")


def read_limits(source: Path) -> dict[str, Decimal]:
    """Lee solo identificadores y máximos; exige cobertura completa del maestro de fronteras."""
    try:
        frontiers = {row["frontera_id"] for row in read_csv((source / "maestros/fronteras.csv").read_bytes())}
        rows = read_csv((source / "maestros/limites_frontera.csv").read_bytes())
        limits = {row["frontera_id"]: Decimal(row["max_kwh"].replace(",", ".")) for row in rows}
        if set(limits) != frontiers or len(rows) != len(limits) or not all(value.is_finite() for value in limits.values()):
            raise ValueError
        return limits
    except Exception:
        raise StreamError("source_error") from None


def produce(source: Path, topic: str, bootstrap: str, deadline: float) -> None:
    """Ejecuta el productor sin shell; timeout mata y espera el subproceso, sin reenviar su stderr."""
    try:
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise StreamError("deadline_exceeded")
        result = subprocess.run([sys.executable, str(ROOT / "tools/producer.py"), "--archivo", str(source),
                                 "--topic", topic, "--bootstrap", bootstrap], cwd=ROOT,
                                capture_output=True, timeout=min(120, remaining), check=False)
        if result.returncode:
            raise StreamError("producer_failed")
    except subprocess.TimeoutExpired:
        raise StreamError("deadline_exceeded") from None
    except OSError:
        raise StreamError("producer_failed") from None


def consume_range(consumer: Any, starts: dict, ends: dict, engine: AlertEngine,
                  deadline: float) -> int:
    """Consume exclusivamente offsets capturados, sin commits ni espera indefinida."""
    if set(starts) != set(ends) or any(ends[part] < start for part, start in starts.items()):
        raise StreamError("incomplete_replay")
    consumer.assign(list(starts))
    for part, offset in starts.items():
        consumer.seek(part, offset)
    consumed, positions = 0, dict(starts)
    while any(positions[part] < end for part, end in ends.items()):
        if monotonic() >= deadline:
            raise StreamError("deadline_exceeded", consumed=consumed)
        for part, records in consumer.poll(timeout_ms=250, max_records=1000).items():
            if part not in ends:
                raise StreamError("incomplete_replay", consumed=consumed)
            for record in records:
                if record.offset < starts[part] or record.offset >= ends[part]:
                    continue
                consumed += 1
                try:
                    engine.accept(record.value)
                except InvalidEvent:
                    raise StreamError("invalid_event", consumed=consumed,
                                      partition=record.partition, offset=record.offset) from None
                positions[part] = record.offset + 1
    if consumed != sum(ends[part] - start for part, start in starts.items()):
        raise StreamError("incomplete_replay", consumed=consumed)
    return consumed


def replay(*, source: Path = ROOT / "data", topic: str = "mediciones.raw",
           bootstrap: str = "127.0.0.1:9092", timeout: float = 250) -> tuple[list[dict], int]:
    """Captura offsets antes/después de publicar y conserva el orden Kafka por frontera."""
    deadline = monotonic() + min(timeout, 250)
    engine = AlertEngine(read_limits(source))
    event_file = source / "eventos/mediciones_stream.ndjson"
    try:
        expected = sum(bool(line.strip()) for line in event_file.read_bytes().splitlines())
        if expected == 0:
            raise ValueError
    except Exception:
        raise StreamError("source_error") from None
    try:
        from kafka import KafkaConsumer, TopicPartition
        from kafka.admin import KafkaAdminClient, NewTopic
        from kafka.errors import TopicAlreadyExistsError
    except ImportError:
        raise StreamError("dependency_missing") from None
    # Las librerías no deben reenviar diagnósticos potencialmente sensibles al log del usuario.
    logger = logging.getLogger("kafka")
    logger.addHandler(logging.NullHandler())
    logger.propagate = False
    admin, consumer = None, None
    stage = "consumer_connection"
    try:
        consumer = KafkaConsumer(bootstrap_servers=bootstrap, group_id=None, enable_auto_commit=False,
                                 request_timeout_ms=10000, session_timeout_ms=6000,
                                 heartbeat_interval_ms=2000, api_version_auto_timeout_ms=5000)
        stage = "topic_metadata"
        partitions = consumer.partitions_for_topic(topic)
        # Consumir un tópico existente no requiere descubrir ni negociar con el controlador.
        if not partitions and topic not in consumer.topics():
            stage = "topic_creation"
            admin = KafkaAdminClient(bootstrap_servers=bootstrap, request_timeout_ms=10000,
                                     api_version_auto_timeout_ms=5000)
            try:
                admin.create_topics([NewTopic(topic, num_partitions=1, replication_factor=1)], timeout_ms=10000)
            except TopicAlreadyExistsError:
                pass
        stage = "topic_metadata"
        metadata_deadline = min(deadline, monotonic() + 10)
        while not partitions and monotonic() < metadata_deadline:
            consumer.topics()  # Refrescar metadatos tras creación o propagación pendiente.
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                sleep(0.1)
        if not partitions:
            raise StreamError("broker_error")
        parts = [TopicPartition(topic, number) for number in sorted(partitions)]
        stage = "start_offsets"
        starts = consumer.end_offsets(parts)
        stage = "producer"
        produce(event_file, topic, bootstrap, deadline)
        stage = "end_offsets"
        if consumer.partitions_for_topic(topic) != partitions:
            raise StreamError("incomplete_replay")
        ends = consumer.end_offsets(parts)
        if sum(ends[part] - starts[part] for part in parts) != expected:
            raise StreamError("incomplete_replay")
        stage = "consume"
        consumed = consume_range(consumer, starts, ends, engine, deadline)
        if monotonic() >= deadline:
            raise StreamError("deadline_exceeded", consumed=consumed)
        stage = "alerts"
        return engine.finish(), consumed
    except StreamError as error:
        if error.stage is None:
            error.stage = stage
        raise
    except Exception:
        raise StreamError("broker_error", stage=stage) from None
    finally:
        try:
            if consumer is not None:
                consumer.close(autocommit=False, timeout_ms=3000)
        finally:
            if admin is not None:
                admin.close()


def main(*, output: Path = ROOT / "out", log_path: Path = ROOT / "logs/pipeline.log",
         connection_factory: Callable[[], Any] | None = None, bootstrap: str | None = None) -> int:
    """Ejecuta streaming, audita su resultado y escribe solo conteos/códigos seguros."""
    start, run_id = monotonic(), str(uuid.uuid4())
    consumed, counts, error = 0, dict.fromkeys(TYPES, 0), None
    try:
        with closing((connection_factory or connect_operational)()) as connection:
            try:
                alerts, consumed = replay() if bootstrap is None else replay(bootstrap=bootstrap)
                counts.update(Counter(item["tipo"] for item in alerts))
                try:
                    publish_files(output, {"alertas.json": json.dumps(alerts, ensure_ascii=True, indent=2) + "\n"})
                except OSError:
                    raise StreamError("publication_error", consumed=consumed) from None
                with connection.cursor() as cursor:
                    record_run(cursor, run_id, consumed, len(alerts), "success", operation="stream")
                connection.commit()
            except Exception as caught:
                connection.rollback()
                if isinstance(caught, StreamError):
                    consumed = caught.consumed or consumed
                try:
                    with connection.cursor() as cursor:
                        record_run(cursor, run_id, consumed, 0, "failed", operation="stream",
                                   rejected=int(isinstance(caught, StreamError) and caught.reason == "invalid_event"))
                    connection.commit()
                except Exception:
                    connection.rollback()
                raise
    except StreamError as caught:
        error = caught
    except PrivacyError:
        error = StreamError("database_error", consumed=consumed)
    except Exception:
        error = StreamError("internal_error", consumed=consumed)
    event = stream_event(consumed=consumed, counts=counts, duration=monotonic() - start,
                         reason=error.reason if error else None, partition=error.partition if error else None,
                         offset=error.offset if error else None)
    if error is not None and error.stage is not None:
        event["stage"] = error.stage
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")
    except OSError:
        event, error = {"event": "stream_failed", "reason": "internal_error"}, StreamError("internal_error")
    print(json.dumps(event))
    return int(error is not None)


if __name__ == "__main__":
    raise SystemExit(main())
