"""Fachada compatible y entrada CLI del flujo de clientes S02."""
from src.client_service import (
    Cipher, Classification, ClientResult, PrivacyError, ROOT, SOURCE_COLUMNS,
    connect_operational, ingest_bytes, main, mask_pii, parse_clients,
    protect_client, record_run, safe_event,
)

__all__ = [
    "Cipher", "Classification", "ClientResult", "PrivacyError", "ROOT", "SOURCE_COLUMNS",
    "connect_operational", "ingest_bytes", "main", "mask_pii", "parse_clients",
    "protect_client", "record_run", "safe_event",
]

if __name__ == "__main__":
    raise SystemExit(main())
