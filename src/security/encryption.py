"""Cifrado autenticado de valores y carga explícita de la llave externa."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat

from src import ROOT
from src.security import PrivacyError


class Cipher:
    """Protege valores con Fernet y los vincula a su contexto, sin almacenar la llave."""
    PREFIX = "fernet:v1:"

    def __init__(self, key: bytes) -> None:
        """Prepara el cifrador con la llave recibida; nunca genera otra."""
        try:
            from cryptography.fernet import Fernet
            self._fernet = Fernet(key)
        except ImportError:
            raise PrivacyError("dependency_missing") from None
        except Exception:
            raise PrivacyError("key_invalid") from None

    @classmethod
    def from_env(cls, root: Path = ROOT) -> "Cipher":
        """Lee la llave externa configurada y conserva los controles de ubicación y permisos."""
        location = os.environ.get("BIA_PII_KEY_FILE")
        if not location:
            raise PrivacyError("key_missing")
        try:
            path = Path(location).resolve(strict=True)
            if not path.is_file() or path.is_relative_to(root.resolve()):
                raise ValueError
            if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
                raise ValueError
            with path.open("rb") as handle:
                key = handle.read(129).strip()
            if len(key) != 44:
                raise ValueError
            return cls(key)
        except PrivacyError:
            raise
        except Exception:
            raise PrivacyError("key_invalid") from None

    def seal(self, value: str, context: str) -> str:
        """Cifra un texto y su contexto con el formato autenticado existente."""
        try:
            envelope = json.dumps({"context": context, "value": value}, ensure_ascii=False).encode("utf-8")
            return self.PREFIX + self._fernet.encrypt(envelope).decode("ascii")
        except Exception:
            raise PrivacyError("cipher_invalid") from None

    def open(self, token: str, context: str) -> str:
        """Verifica el token y su contexto antes de devolver el texto original."""
        try:
            if not token.startswith(self.PREFIX):
                raise ValueError
            envelope = json.loads(self._fernet.decrypt(token[len(self.PREFIX):].encode("ascii")))
            if envelope["context"] != context or not isinstance(envelope["value"], str):
                raise ValueError
            return envelope["value"]
        except Exception:
            raise PrivacyError("cipher_invalid") from None
