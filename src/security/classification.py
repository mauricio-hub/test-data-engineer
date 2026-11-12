"""Política efectiva y contratos de columnas de clientes, consumos y facturación."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from src import ROOT
from src.security import PrivacyError
from src.security.encryption import Cipher


SOURCE_COLUMNS = (
    "cliente_id", "razon_social", "nit", "email_contacto", "celular_contacto",
    "direccion", "ciudad", "departamento", "representante_legal", "observaciones",
)
MODEL = {
    "core.clientes": set(SOURCE_COLUMNS) | {"observaciones_con_pii", "source_sha256"},
    "core.clientes_cuarentena": {"source_sha256", "record_number", "reason", "payload"},
    "analytics.v_clientes": {"cliente_id"},
    "audit.runs": {"run_id", "actor", "operation", "recorded_at", "rows_read", "rows_loaded", "rows_rejected", "result"},
}
CLIENT_TABLES = tuple(MODEL)
MODEL.update({
    "core.fronteras": {"frontera_id", "codigo_sic", "cliente_id", "mercado", "operador_red", "nivel_tension", "fecha_registro", "estado"},
    "core.limites_frontera": {"frontera_id", "min_kwh", "max_kwh"},
    "core.archivos_ingesta": {"archivo", "source_sha256", "estado", "filas_leidas", "filas_rechazadas"},
    "core.estado_lectura": {"frontera_id", "timestamp", "version_lectura", "archivo", "fila", "valida"},
    "core.fact_consumo_horario": {"frontera_id", "timestamp", "consumo_kwh", "calidad_lectura"},
    "core.consumos_cuarentena": {"archivo", "source_sha256", "fila", "motivo", "payload"},
})
BILLING_MODEL = {
    "core.archivos_facturacion": {"archivo", "source_sha256", "estado", "filas_leidas", "filas_rechazadas"},
    "core.facturas": {"factura_id", "frontera_id", "periodo", "consumo_facturado_kwh", "tarifa_cop_kwh", "valor_total_cop", "archivo", "payload"},
    "core.factura_componentes": {"factura_id", "posicion", "valor_cop_kwh", "payload"},
    "core.facturas_cuarentena": {"archivo", "source_sha256", "fila", "motivo", "payload"},
    "analytics.v_consumo_mensual": {"frontera_id", "mes", "consumo_kwh", "horas_con_dato"},
}

class Classification:
    """Comprueba la política por columna y aplica la protección del modelo conocido."""
    LEVELS = {"Público", "Interno", "Confidencial", "Restringido-PII"}

    def __init__(self, tables: dict) -> None:
        """Valida cobertura, etiquetas y límites de protección antes de aceptar la política."""
        try:
            expected = MODEL | BILLING_MODEL if set(tables) == set(MODEL | BILLING_MODEL) else MODEL
            if set(tables) != set(expected):
                raise ValueError
            for table, columns in expected.items():
                if set(tables[table]) != columns or not set(tables[table].values()) <= self.LEVELS:
                    raise ValueError
            # No permitir degradar datos conocidos como sensibles a texto claro.
            for column in SOURCE_COLUMNS[1:]:
                if tables["core.clientes"][column] != "Restringido-PII":
                    raise ValueError
            if tables["core.clientes_cuarentena"]["payload"] != "Restringido-PII":
                raise ValueError
            if tables["core.consumos_cuarentena"]["payload"] != "Restringido-PII":
                raise ValueError
            encryptable = {("core.clientes", c) for c in SOURCE_COLUMNS[1:]} | {
                ("core.clientes_cuarentena", "payload"), ("core.consumos_cuarentena", "payload")}
            for table in ("core.facturas", "core.factura_componentes", "core.facturas_cuarentena"):
                if table in tables:
                    if tables[table]["payload"] != "Restringido-PII":
                        raise ValueError
                    encryptable.add((table, "payload"))
            for table, columns in tables.items():
                for column, label in columns.items():
                    if label == "Restringido-PII" and (table, column) not in encryptable:
                        # No guardar una columna técnica en claro si alguien la reclasifica como PII.
                        raise ValueError
            if tables["core.clientes"]["cliente_id"] != "Interno" or tables["analytics.v_clientes"]["cliente_id"] != "Interno":
                raise ValueError
            self.tables = {t: dict(c) for t, c in tables.items()}
        except Exception:
            raise PrivacyError("classification_invalid") from None

    @classmethod
    def load(cls, path: Path = ROOT / "data_classification.yaml", *, include_billing: bool = False) -> "Classification":
        """Lee la política YAML segura y rechaza configuraciones incompatibles."""
        try:
            import yaml
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
            if document["version"] != 1:
                raise ValueError
            if set(document["tables"]) != set(MODEL | BILLING_MODEL):
                raise ValueError
            full = cls(document["tables"])
            # Clientes y S03 conservan su ámbito sin exigir que SQL 004 ya exista.
            return full if include_billing else cls({name: full.tables[name] for name in MODEL})
        except Exception:
            raise PrivacyError("classification_invalid") from None

    def validate_database(self, connection: Any, tables: tuple[str, ...] = CLIENT_TABLES) -> None:
        """Verifica columnas del ámbito solicitado; clientes conserva su contrato S02."""
        try:
            with connection.cursor() as cursor:
                for name in tables:
                    expected = (MODEL | BILLING_MODEL)[name]
                    schema, table = name.split(".")
                    # El catálogo permite verificar columnas sin dar SELECT sobre auditoría.
                    cursor.execute("SELECT a.attname FROM pg_catalog.pg_attribute a "
                                   "JOIN pg_catalog.pg_class c ON c.oid=a.attrelid "
                                   "JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace "
                                   "WHERE n.nspname=%s AND c.relname=%s AND a.attnum>0 AND NOT a.attisdropped",
                                   (schema, table))
                    if {r[0] for r in cursor.fetchall()} != expected:
                        raise ValueError
        except Exception:
            raise PrivacyError("classification_invalid") from None

    def protect(self, table: str, column: str, value: str, context: str, cipher: Cipher) -> str:
        """Aplica cifrado cuando la clasificación de la columna lo exige."""
        try:
            level = self.tables[table][column]
        except (KeyError, TypeError):
            raise PrivacyError("classification_invalid") from None
        return cipher.seal(value, context) if level == "Restringido-PII" else value
