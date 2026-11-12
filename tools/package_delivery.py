"""Construye una entrega revisable con biblioteca estándar; no ejecuta el pipeline ni cambia Git."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ROOT_FILES = {"README.md", "Makefile", "docker-compose.yml", "requirements.txt", "data_classification.yaml",
              "SECURITY.md", "THREAT_MODEL.md", "DECISIONS.md", "AI_USAGE.md", "RUNBOOK.md", "AGENTS.md",
              ".gitignore", ".env.example", "entrega.example.yaml", "entrega.yaml"}
SOURCE_DIRS = {"src", "sql", "tools", "tests", "specs", "docs", "infra", "plantillas"}
REQUIRED = {"README.md", "Makefile", "docker-compose.yml", "requirements.txt", "data_classification.yaml",
            "SECURITY.md", "THREAT_MODEL.md", "DECISIONS.md", "AI_USAGE.md", "RUNBOOK.md", "entrega.yaml",
            "infra/main.tf", ".git/HEAD", ".git/config"}
REQUIRED |= {"src/__init__.py", "src/batch/pipeline.py", "src/streaming/consumer.py",
             "tools/manage.py", "tools/producer.py", "tools/verificar_entrega.py", "tests/test_setup.py",
             "sql/001_access.sql", "sql/002_clients.sql", "sql/003_consumptions.sql", "sql/004_billing.sql"}
EXCLUDED_DIRS = {"data", ".local", ".venv", ".audit-venv", "venv", "env", "node_modules", "__pycache__",
                 ".terraform", ".pytest_cache", ".mypy_cache", ".ruff_cache", "out", "logs", "volumes",
                 "pgdata", "rpdata", "dist"}
PRIVATE_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".pyc", ".tfplan", ".tfvars", ".zip", ".mp4", ".mov"}
SECRET_PATTERNS = (
    rb"-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
    rb"AKIA[0-9A-Z]{16}", rb"gh[pousr]_[A-Za-z0-9]{30,}", rb"https?://[^/\s]+:[^/\s]+@",
)


class PackageError(Exception):
    """Expone fallos cerrados sin imprimir archivos, secretos ni errores externos."""


def excluded(path: str) -> bool:
    """Excluye material privado también en carpetas anidadas; permite el lockfile Terraform."""
    parts = PurePosixPath(path).parts
    name = parts[-1] if parts else ""
    if any(part in EXCLUDED_DIRS for part in parts):
        return True
    if name == ".terraform.lock.hcl":
        return False
    return (name == ".env" or name.startswith(".env.") and name != ".env.example"
            or name in {"id_rsa", "id_ed25519", "credentials", "terraform.rc", ".terraformrc"}
            or PurePosixPath(name).suffix.lower() in PRIVATE_SUFFIXES
            or ".tfstate" in name or name.endswith(".tfvars.json") or name.endswith(".lock")
            or name.startswith("crash."))


def linked(path: Path) -> bool:
    """Detecta enlaces y reparse points Windows para impedir salir del árbol autorizado."""
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0))


def secret_content(data: bytes, secrets: list[bytes]) -> bool:
    """Busca patrones concretos y credenciales locales conocidas; no promete detección universal."""
    return any(value in data for value in secrets) or any(re.search(pattern, data) for pattern in SECRET_PATTERNS)


def git(root: Path, *args: str) -> bytes:
    """Ejecuta consultas Git de solo lectura sin reenviar diagnósticos del entorno."""
    try:
        result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise PackageError("No se pudo revisar el historial Git.") from None
    if result.returncode:
        raise PackageError("No se pudo revisar el historial Git.")
    return result.stdout


def known_secrets(root: Path) -> list[bytes]:
    """Lee solo contraseñas de evaluación locales para impedir su copia fuera del manifiesto."""
    path = root / ".local/evaluation.json"
    if not path.exists():
        return []
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return [state[name]["password"].encode() for name in ("superusuario", "ingesta", "analista", "auditor")]
    except (KeyError, TypeError, ValueError, OSError):
        raise PackageError("No se pudo revisar el estado local sin exponer secretos.") from None


def audit_history(root: Path, secrets: list[bytes]) -> None:
    """Revisa todos los objetos Git, incluso no referenciados, sin modificar ni recortar historia."""
    directory = root / ".git"
    if not directory.is_dir() or linked(directory) or (directory / "objects/info/alternates").exists() or (directory / "shallow").exists():
        raise PackageError("Se requiere un historial Git completo, local y autocontenido.")
    git(root, "fsck", "--full")
    listing = git(root, "cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
    for line in listing.decode("ascii").splitlines():
        oid, kind = line.split()
        if kind == "blob" and secret_content(git(root, "cat-file", "blob", oid), secrets):
            raise PackageError("El historial contiene un posible secreto; revisar antes de empaquetar.")
        if kind == "commit":
            paths = git(root, "ls-tree", "-r", "--name-only", "-z", oid).decode("utf-8").split("\0")
            if any(path and (excluded(path) or path == "entrega.yaml") for path in paths):
                raise PackageError("El historial conserva material excluido de la entrega.")


def collect(root: Path, secrets: list[bytes]) -> list[tuple[str, Path]]:
    """Recoge únicamente fuentes/documentos permitidos y Git, sin seguir enlaces ni cachés."""
    files = []
    for directory, dirs, names in os.walk(root, followlinks=False):
        base = Path(directory)
        relative = base.relative_to(root)
        kept = []
        for name in sorted(dirs):
            path = base / name
            local = path.relative_to(root)
            if relative == Path(".") and name not in SOURCE_DIRS | {".git"}:
                continue
            if name in EXCLUDED_DIRS or local.parts[:2] == (".git", "hooks"):
                continue
            if linked(path):
                raise PackageError("Hay un enlace en el contenido permitido; no se sigue automáticamente.")
            kept.append(name)
        dirs[:] = kept
        for name in sorted(names):
            path = base / name
            local = path.relative_to(root).as_posix()
            if relative == Path(".") and name not in ROOT_FILES:
                continue
            if excluded(local) or local in {".git/COMMIT_EDITMSG", ".git/FETCH_HEAD", ".git/ORIG_HEAD"}:
                continue
            if linked(path) or not path.is_file():
                raise PackageError("Hay un archivo enlazado o especial en el contenido permitido.")
            if local != "entrega.yaml" and secret_content(path.read_bytes(), secrets):
                raise PackageError("Se detectó un posible secreto fuera del manifiesto permitido.")
            files.append((local, path))
    names = {name for name, _ in files}
    if not REQUIRED <= names:
        raise PackageError("Faltan archivos obligatorios para construir la entrega.")
    return files


def inspect_archive(path: Path, name: str) -> dict[str, int]:
    """Valida CRC, rutas seguras, exclusiones y archivos obligatorios del ZIP construido."""
    with zipfile.ZipFile(path) as archive:
        members = archive.infolist()
        names = [item.filename for item in members]
        if len(names) != len(set(names)) or archive.testzip() is not None:
            raise PackageError("ZIP duplicado o con contenido dañado.")
        relative_names = set()
        for item in members:
            parts = PurePosixPath(item.filename).parts
            if not parts or parts[0] != name or ".." in parts or "\\" in item.filename or ":" in item.filename or item.filename.startswith("/"):
                raise PackageError("El ZIP contiene una ruta no permitida.")
            local = "/".join(parts[1:])
            empty_output = item.is_dir() and local == "out"
            if stat.S_ISLNK(item.external_attr >> 16) or (local and excluded(local) and not empty_output) or local.startswith(".git/hooks/"):
                raise PackageError("El ZIP contiene enlaces o material excluido.")
            if not item.is_dir():
                relative_names.add(local)
        if not REQUIRED <= relative_names:
            raise PackageError("El ZIP no contiene todos los entregables obligatorios.")
        return {"files": len(relative_names), "bytes": path.stat().st_size}


def build_package(root: Path, destination: Path, name: str) -> Path:
    """Crea un ZIP nuevo auditado; nunca reemplaza paquetes previos ni altera el proyecto."""
    if not re.fullmatch(r"[a-z]+_[a-z]+(?:_[a-z]+)*", name):
        raise PackageError("Usar apellido_nombre en minúsculas, sin tildes ni separadores de ruta.")
    root = root.resolve(strict=True)
    if destination.resolve().is_relative_to(root / ".git"):
        raise PackageError("El destino no puede modificar los metadatos Git.")
    target = destination / (name + ".zip")
    if target.exists():
        raise PackageError("El paquete ya existe; elegir otro destino sin sobrescribirlo.")
    secrets = known_secrets(root)
    audit_history(root, secrets)
    files = collect(root, secrets)
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="bia-package-", dir=destination) as directory:
        staged = Path(directory) / "delivery.zip"
        with zipfile.ZipFile(staged, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(name + "/out/", b"")
            for local, path in files:
                archive.write(path, name + "/" + local)
        inspect_archive(staged, name)
        # Apertura exclusiva evita sobrescritura incluso si aparece otro archivo durante la revisión.
        with target.open("xb") as output, staged.open("rb") as source:
            shutil.copyfileobj(source, output)
    return target


def main() -> int:
    """Ofrece empaquetado explícito después de completar candidato y validaciones finales."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True, help="apellido_nombre; no se deriva de datos personales")
    parser.add_argument("--destination", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    try:
        path = build_package(ROOT, args.destination, args.name)
        print(json.dumps({"package": path.name, **inspect_archive(path, args.name)}))
        return 0
    except (PackageError, OSError, ValueError, zipfile.BadZipFile):
        print("No se creó una entrega válida; revisar requisitos, exclusiones e historial sin exponer secretos.")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
