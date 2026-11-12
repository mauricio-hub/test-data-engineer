"""Calcula calidad estable y publica archivos completos sin información personal."""
from __future__ import annotations

import calendar
import csv
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import io
import json
import os
from pathlib import Path
import tempfile

from src.batch.extract import read_csv
from src.batch.transform import normalize

DQ_KEYS = (
    "filas_leidas", "duplicados_exactos", "duplicados_conflictivos", "registros_negativos",
    "registros_nulos", "registros_outlier", "registros_mwh_convertidos", "correcciones_tardias_aplicadas",
    "horas_sin_lectura_valida_total", "horas_sin_lectura_valida_por_frontera",
    "fronteras_huerfanas_facturacion", "clientes_con_pii_en_texto_libre",
)
CSV_HEADER = ("frontera_id", "mes", "consumo_kwh", "horas_con_dato")


def quality_report(source: Path, context: dict) -> dict:
    """Relee solo entradas aceptadas para describir el conjunto, no las escrituras del intento."""
    report = dict.fromkeys(DQ_KEYS, 0)
    seen, winners, months = {}, {}, set()
    reasons = {"negative": "registros_negativos", "empty": "registros_nulos", "outlier": "registros_outlier"}
    for name, digest in context["files"]:
        data = (source / "consumos" / name).read_bytes()
        # Sin copia raw SQL, no publicar un reporte de entradas diferentes a las confirmadas.
        if hashlib.sha256(data).hexdigest() != digest:
            raise ValueError("La entrada aceptada ya no coincide con su registro.")
        raw_rows = read_csv(data)
        for reading, raw in zip(normalize(raw_rows), raw_rows):
            report["filas_leidas"] += 1
            months.add(reading.timestamp.strftime("%Y-%m"))
            if reading.reason:
                report[reasons[reading.reason]] += 1
            report["registros_mwh_convertidos"] += int(raw.get("unidad", "").strip() == "MWh")
            key = (reading.frontier, reading.timestamp)
            signature = (reading.kwh, reading.version, reading.quality)
            signatures = seen.setdefault(key, set())
            if signatures:
                report["duplicados_exactos" if signature in signatures else "duplicados_conflictivos"] += 1
            signatures.add(signature)
            rank = (reading.version, name, reading.number)
            previous = winners.get(key)
            if previous is None or rank > previous:
                if previous is not None and reading.version > previous[0]:
                    report["correcciones_tardias_aplicadas"] += 1
                winners[key] = rank
    hours = sum(calendar.monthrange(int(month[:4]), int(month[5:]))[1] * 24 for month in months)
    valid_hours = dict.fromkeys(context["frontiers"], 0)
    for frontier, month, _, count in context["monthly"]:
        if month not in months:
            raise ValueError("La base contiene un mes sin entrada aceptada disponible.")
        valid_hours[frontier] += count
    gaps = {frontier: hours - count for frontier, count in valid_hours.items()}
    if any(value < 0 for value in gaps.values()):
        raise ValueError("El calendario y los hechos horarios no concilian.")
    report["horas_sin_lectura_valida_por_frontera"] = gaps
    report["horas_sin_lectura_valida_total"] = sum(gaps.values())
    report["fronteras_huerfanas_facturacion"] = context["orphans"]
    report["clientes_con_pii_en_texto_libre"] = context["pii_clients"]
    return report


def monthly_csv(rows: list) -> str:
    """Exporta la suma exacta a tres decimales, redondeando solo al final."""
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(CSV_HEADER)
    for frontier, month, amount, count in rows:
        writer.writerow((frontier, month, format(amount.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP), ".3f"), count))
    return output.getvalue()


def publish(directory: Path, monthly: str, quality: dict, metrics: dict) -> None:
    """Prepara los tres archivos antes de reemplazarlos; un fallo nunca se anuncia como éxito."""
    documents = {"consumo_mensual.csv": monthly,
                 "dq_report.json": json.dumps(quality, ensure_ascii=True, indent=2, allow_nan=False) + "\n",
                 "metrics.json": json.dumps(metrics, ensure_ascii=True, indent=2, allow_nan=False) + "\n"}
    directory.mkdir(parents=True, exist_ok=True)
    staged = []
    try:
        for name, content in documents.items():
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="", dir=directory,
                                             prefix=".bia-", suffix=".tmp", delete=False) as handle:
                staged.append((Path(handle.name), directory / name))
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())
        for temporary, target in staged:
            os.replace(temporary, target)
    finally:
        for temporary, _ in staged:
            temporary.unlink(missing_ok=True)
