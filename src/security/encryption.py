"""Cifrado autenticado de valores y lectura de llaves externas persistentes."""
from __future__ import annotations

import json
from pathlib import Path

from src import ROOT
from src.security import PrivacyError
from src.security.keys import load_key


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
    def from_env(cls, root: Path = ROOT, scope: str = "evaluation") -> "Cipher":
        """Lee la llave explícita o persistente; los comandos de carga nunca generan llaves."""
        return cls(load_key(root, scope))

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
