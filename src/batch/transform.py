"""Normaliza consumos según B1–B4 y separa importes y datos privados de facturación."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re

from src.batch.extract import InputError

# Colombia usa UTC-5 fijo (B1); evita depender de una base tzdata externa en Windows.
BOGOTA = timezone(timedelta(hours=-5), "America/Bogota")
FORMATS = (
    {"frontera_id", "timestamp", "consumo_kwh", "version_lectura", "calidad_lectura"},
    {"frontera_id", "timestamp_utc", "consumo_kwh", "version_lectura", "calidad_lectura"},
    {"frontera_id", "timestamp", "kwh", "unidad", "version_lectura", "calidad_lectura"},
)


@dataclass(frozen=True)
class Reading:
    """Representa una lectura interpretable, incluso cuando B4 invalida su consumo."""

    frontier: str
    timestamp: datetime
    version: int
    number: int
    kwh: Decimal | None
    quality: str
    reason: str | None


def normalize(rows: list[dict[str, str]]) -> list[Reading]:
    """Normaliza el archivo entero; una estructura ininterpretable rechaza todo el archivo."""
    result = []
    try:
        if not rows or set(rows[0]) not in FORMATS:
            raise ValueError
        for number, row in enumerate(rows, 1):
            frontier = row["frontera_id"].strip()
            if not re.fullmatch(r"CO[0-9]{10}", frontier):
                raise ValueError
            stamp = datetime.fromisoformat(row.get("timestamp", row.get("timestamp_utc", "")).strip().replace("Z", "+00:00"))
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc if "timestamp_utc" in row else BOGOTA)
            stamp = stamp.astimezone(BOGOTA)
            version = int(row["version_lectura"])
            raw = row.get("consumo_kwh", row.get("kwh", "")).strip()
            unit = row.get("unidad", "kWh").strip()
            if unit not in ("kWh", "MWh"):
                raise ValueError
            kwh = Decimal(raw.replace(",", ".")) if raw else None
            if kwh is not None:
                if not kwh.is_finite():
                    raise ValueError
                if unit == "MWh":
                    kwh *= 1000
            reason = "empty" if kwh is None else "negative" if kwh < 0 else "outlier" if kwh > 1_000_000 else None
            result.append(Reading(frontier, stamp, version, number, kwh, row["calidad_lectura"], reason))
        return result
    except (ValueError, KeyError, InvalidOperation, OverflowError):
        raise InputError() from None


def normalize_billing(document: dict) -> list[dict]:
    """Separa importes, componentes y datos privados sin registrar contenido personal."""
    try:
        period = document["periodo"]
        if not isinstance(period, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}", period):
            raise ValueError
        datetime.strptime(period, "%Y-%m")
        result, seen = [], set()
        for raw in document["facturas"]:
            identifier, frontier = raw["factura_id"], raw["frontera_id"]
            if not isinstance(identifier, str) or not identifier or identifier in seen or not isinstance(frontier, str):
                raise ValueError
            seen.add(identifier)
            amounts = tuple(Decimal(str(raw[column])) for column in ("consumo_facturado_kwh", "tarifa_cop_kwh", "valor_total_cop"))
            components = [(Decimal(str(item["valor_cop_kwh"])), {"concepto": item["concepto"]}) for item in raw["componentes"]]
            if not all(value.is_finite() for value in (*amounts, *(item[0] for item in components))):
                raise ValueError
            private = {"emisor": document.get("emisor"), "generado_en": document.get("generado_en"),
                       "cliente": raw.get("cliente"), "metodo_pago": raw.get("metodo_pago")}
            result.append({"id": identifier, "frontier": frontier, "period": period + "-01",
                           "amounts": amounts, "components": components, "private": private, "raw": raw})
        return result
    except (KeyError, ValueError, TypeError, InvalidOperation):
        raise InputError() from None
