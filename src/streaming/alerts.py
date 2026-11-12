"""Aplica las tres reglas del README sin depender de Kafka ni del reloj real."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import json
import re

DAY_START = datetime(2026, 6, 1, tzinfo=timezone(timedelta(hours=-5)))
TYPES = ("FRONTERA_SIN_REPORTE", "CONSUMO_FUERA_DE_BANDA", "LECTURA_RETROACTIVA")


class InvalidEvent(Exception):
    """Rechaza un evento sin incluir su contenido en el mensaje público."""

    def __init__(self) -> None:
        """Expone exclusivamente un mensaje estático."""
        super().__init__("Evento inválido; consulte la posición técnica en Kafka.")


class AlertEngine:
    """Mantiene el máximo temporal y la presencia por intervalo para cada frontera."""

    def __init__(self, limits: dict[str, Decimal]) -> None:
        """Recibe máximos del maestro y prepara estado exclusivo de esta reproducción."""
        self.limits = limits
        self.latest: dict[str, datetime] = {}
        self.present = {frontier: set() for frontier in limits}
        self.alerts: set[tuple[str, str, datetime]] = set()

    def accept(self, data: bytes) -> None:
        """Valida campos necesarios; ignora texto libre y objetos adicionales como medidor."""
        try:
            event = json.loads(data.decode("utf-8"), parse_float=Decimal)
            frontier, raw_stamp, raw_kwh = event["frontera_id"], event["ts_medicion"], event["kwh"]
            if not isinstance(frontier, str) or not re.fullmatch(r"CO[0-9]{10}", frontier) or frontier not in self.limits:
                raise ValueError
            if not isinstance(raw_stamp, str) or isinstance(raw_kwh, bool) or not isinstance(raw_kwh, (int, float, Decimal)):
                raise ValueError
            stamp = datetime.fromisoformat(raw_stamp.replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                raise ValueError
            stamp = stamp.astimezone(DAY_START.tzinfo)
            elapsed = (stamp - DAY_START).total_seconds()
            kwh = Decimal(str(raw_kwh))
            if not kwh.is_finite() or not 0 <= elapsed < 86400 or elapsed % 900:
                raise ValueError
        except (ValueError, TypeError, KeyError, UnicodeError, InvalidOperation, AttributeError, OverflowError):
            raise InvalidEvent() from None
        if kwh > self.limits[frontier]:
            self.alerts.add(("CONSUMO_FUERA_DE_BANDA", frontier, stamp))
        previous = self.latest.get(frontier)
        if previous is not None and stamp < previous:
            self.alerts.add(("LECTURA_RETROACTIVA", frontier, stamp))
        if previous is None or stamp > previous:
            self.latest[frontier] = stamp
        self.present[frontier].add(int(elapsed // 900))

    def finish(self) -> list[dict[str, str]]:
        """Evalúa ausencia al cierre; recuperación reinicia la racha, incluida la hora final."""
        for frontier, intervals in self.present.items():
            missing = 0
            for index in range(96):
                missing = 0 if index in intervals else missing + 1
                if missing == 3:
                    self.alerts.add(("FRONTERA_SIN_REPORTE", frontier, DAY_START + timedelta(minutes=15 * index)))
        return [{"tipo": kind, "frontera_id": frontier, "ts": stamp.isoformat()}
                for kind, frontier, stamp in sorted(self.alerts)]
