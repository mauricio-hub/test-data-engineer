"""Descubre archivos y lee CSV o JSON completos antes de modificar la base."""
from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from pathlib import Path


class InputError(Exception):
    """Comunica un rechazo de estructura sin incluir contenido del archivo."""

    def __init__(self, reason: str = "invalid_file") -> None:
        """Conserva únicamente motivos controlados por la aplicación."""
        self.reason = reason
        super().__init__("Archivo rechazado; consulte la cuarentena protegida.")


def discover(directory: Path) -> list[Path]:
    """Devuelve todos los archivos, ordenados por nombre, sin una lista de meses."""
    return sorted((path for path in directory.iterdir() if path.is_file()), key=lambda p: p.name)


def read_csv(data: bytes) -> list[dict[str, str]]:
    """Lee coma o punto y coma, UTF-8 o Windows-1252, preservando filas citadas."""
    try:
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = data.decode("cp1252")
        header = text.splitlines()[0]
        delimiter = ";" if header.count(";") > header.count(",") else ","
        reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        if not reader.fieldnames or len(set(reader.fieldnames)) != len(reader.fieldnames):
            raise ValueError
        rows = list(reader)
        if not rows or any(None in row or None in row.values() for row in rows):
            raise ValueError
        return rows
    except (ValueError, IndexError, UnicodeError, csv.Error):
        raise InputError() from None


def read_billing(data: bytes) -> dict:
    """Lee JSON sin aproximación binaria y exige un sobre con lista de facturas."""
    try:
        document = json.loads(data.decode("utf-8-sig"), parse_float=Decimal)
        if not isinstance(document, dict) or not isinstance(document.get("facturas"), list):
            raise ValueError
        return document
    except (ValueError, UnicodeError):
        raise InputError() from None
