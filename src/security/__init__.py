"""Errores públicos de seguridad con mensajes cerrados; no depende de coordinadores."""
from __future__ import annotations

MESSAGES = {
    "key_missing": "Falta la llave PII. Prepare una instalación nueva con setup o restaure la llave existente; BIA_PII_KEY_FILE permite indicar su ruta.",
    "key_initialization_blocked": "No se creó la llave: hay una instalación previa o no pudo comprobarse su ausencia. Restaure la llave existente y revise Docker.",
    "key_invalid": "La llave PII no es válida o no tiene protección adecuada.",
    "cipher_invalid": "No se pudo verificar el dato cifrado; revise la llave y la integridad.",
    "classification_invalid": "La clasificación no cubre el modelo o permite una protección insuficiente.",
    "csv_invalid": "No se pudo interpretar el maestro de clientes; no se aplicaron sus filas.",
    "client_id_invalid": "El maestro contiene un identificador de cliente inválido.",
    "client_duplicate": "El maestro contiene identificadores de cliente repetidos.",
    "source_unavailable": "No se pudo leer el archivo de clientes.",
    "database_error": "No se pudo completar la operación en PostgreSQL.",
    "internal_error": "La operación no pudo completarse.",
    "dependency_missing": "Falta una dependencia de S02; ejecute make setup.",
}


class PrivacyError(Exception):
    """Solo admite códigos cerrados: ningún mensaje incorpora datos de entrada."""
    def __init__(self, code: str) -> None:
        """Convierte el código conocido en un mensaje seguro y estable."""
        self.code = code if code in MESSAGES else "internal_error"
        super().__init__(MESSAGES[self.code])
