"""Resuelve y prepara llaves persistentes sin sustituir secretos existentes."""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
import subprocess

from src import ROOT
from src.security import PrivacyError


def key_path(scope: str = "evaluation") -> Path:
    """Prioriza la ruta explícita; separa la llave automática de evaluación y demo."""
    if scope not in ("evaluation", "demo"):
        raise PrivacyError("key_invalid")
    if "BIA_PII_KEY_FILE" in os.environ:
        if not os.environ["BIA_PII_KEY_FILE"]:
            raise PrivacyError("key_missing")
        return Path(os.environ["BIA_PII_KEY_FILE"])
    base = (Path(os.environ["LOCALAPPDATA"]) if os.name == "nt"
            else Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))))
    folder = base / "BiaEnergySecrets"
    return folder / ("pii.fernet.key" if scope == "evaluation" else "demo/pii.fernet.key")


def load_key(root: Path = ROOT, scope: str = "evaluation") -> bytes:
    """Lee y valida una llave sin generarla, repararla ni divulgarla."""
    try:
        from cryptography.fernet import Fernet
        location = key_path(scope)
        if not location.exists():
            raise PrivacyError("key_missing")
        path = location.resolve(strict=True)
        if not path.is_file() or path.is_relative_to(root.resolve()):
            raise ValueError
        if os.name != "nt" and stat.S_IMODE(path.stat().st_mode) & 0o077:
            raise ValueError
        with path.open("rb") as handle:
            key = handle.read(129).strip()
        if len(key) != 44:
            raise ValueError
        Fernet(key)
        return key
    except PrivacyError:
        raise
    except Exception:
        raise PrivacyError("key_invalid") from None


def docker_output(args: list[str]) -> str:
    """Exige comprobaciones Docker exitosas; nunca reenvía su salida de error."""
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            encoding="utf-8", timeout=20, check=False)
    if result.returncode:
        raise PrivacyError("key_initialization_blocked")
    return result.stdout


def require_fresh_install(root: Path, scope: str) -> None:
    """Bloquea la generación ante evidencia local o Docker de una instalación previa."""
    local = root / ".local" if scope == "evaluation" else root / ".local/demo"
    evidence = (("evaluation.json", "ingesta.json", "postgres_password") if scope == "evaluation"
                else ("state.json", "postgres_password"))
    if any((local / name).exists() for name in evidence):
        raise PrivacyError("key_initialization_blocked")
    project = "bia-evaluation" if scope == "evaluation" else "bia-demo"
    # Detectar incluso volúmenes detenidos o un clon nuevo contra una instalación anterior.
    volumes = docker_output(["volume", "ls", "--format", "{{.Name}}"])
    labelled = docker_output(["volume", "ls", "--filter", f"label=com.docker.compose.project={project}",
                              "--format", "{{.Name}}"])
    containers = docker_output(["ps", "-aq", "--filter", f"label=com.docker.compose.project={project}"])
    if project + "_pgdata" in volumes.splitlines() or labelled.strip() or containers.strip():
        raise PrivacyError("key_initialization_blocked")
    # Un servidor ajeno a Compose en el puerto de destino también invalida la prueba de instalación nueva.
    port = 55433 if scope == "demo" else int(os.environ.get("PG_PORT", "55432"))
    try:
        connection = socket.create_connection(("127.0.0.1", port), timeout=5)
    except ConnectionRefusedError:
        return
    except OSError:
        raise PrivacyError("key_initialization_blocked") from None
    connection.close()
    raise PrivacyError("key_initialization_blocked")


def secure_directory(path: Path) -> None:
    """Restringe el directorio de llaves antes de crear un archivo con contenido secreto."""
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if os.name == "nt":
        # Reemplazar la ACL, no solo añadir un permiso: podrían existir concesiones amplias explícitas.
        script = ("$ErrorActionPreference='Stop'; "
                  "$sid=[System.Security.Principal.WindowsIdentity]::GetCurrent().User; "
                  "$acl=New-Object System.Security.AccessControl.DirectorySecurity; "
                  "$acl.SetOwner($sid); $acl.SetAccessRuleProtection($true,$false); "
                  "$rule=New-Object System.Security.AccessControl.FileSystemAccessRule("
                  "$sid,'FullControl','ContainerInherit,ObjectInherit','None','Allow'); "
                  "$acl.AddAccessRule($rule); Set-Acl -LiteralPath $env:BIA_KEY_DIRECTORY -AclObject $acl")
        environment = dict(os.environ, BIA_KEY_DIRECTORY=str(path))
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                       env=environment, capture_output=True, check=True, timeout=15)
    else:
        path.chmod(0o700)


def initialize_key(root: Path = ROOT, scope: str = "evaluation") -> None:
    """Crea una llave solo en instalación nueva; reutiliza las existentes sin escribirlas."""
    try:
        from cryptography.fernet import Fernet
        path = key_path(scope)
        # Una configuración explícita nunca autoriza crear o sustituir ese archivo.
        if "BIA_PII_KEY_FILE" in os.environ or path.exists() or path.is_symlink():
            load_key(root, scope)
            return
        if path.resolve().is_relative_to(root.resolve()):
            raise PrivacyError("key_invalid")
        require_fresh_install(root, scope)
        secure_directory(path.parent)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            load_key(root, scope)
            return
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(Fernet.generate_key())
            handle.flush()
            os.fsync(handle.fileno())
        load_key(root, scope)
    except PrivacyError:
        raise
    except Exception:
        raise PrivacyError("key_initialization_blocked") from None
