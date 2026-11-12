#!/usr/bin/env python3
"""Prepara el entorno y dirige comandos al pipeline, sin generar una llave PII."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ROLES = {"ingesta": "rol_ingesta", "analista": "rol_analista", "auditor": "rol_auditor"}


class SetupError(Exception):
    """Error operativo que puede mostrarse sin revelar entradas o secretos."""


def private_write(path: Path, content: str) -> None:
    """Archivo privado en POSIX; en Windows se aplica la ACL del directorio."""
    temporary = path.with_name(path.name + ".tmp")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    temporary.replace(path)
    path.chmod(0o600)


def load_state(root: Path = ROOT) -> dict:
    try:
        state = json.loads((root / ".local/evaluation.json").read_text(encoding="utf-8"))
        if state["host"] != "127.0.0.1" or state["database"] != "bia_datos":
            raise ValueError
        if type(state["port"]) is not int or not 1024 <= state["port"] <= 65535:
            raise ValueError
        for name, user in {"superusuario": "postgres", **ROLES}.items():
            account = state[name]
            if account["usuario"] != user or not re.fullmatch(r"[a-f0-9]{64}", account["password"]):
                raise ValueError
        if len({state[name]["password"] for name in ("superusuario", *ROLES)}) != 4:
            raise ValueError
        return state
    except (OSError, ValueError, KeyError, TypeError):
        raise SetupError("Configuración local ausente o inválida; ejecutar setup. No se rotan secretos automáticamente.") from None


def prepare(root: Path = ROOT) -> dict:
    local = root / ".local"
    local.mkdir(mode=0o700, exist_ok=True)
    local.chmod(0o700)
    state_path = local / "evaluation.json"
    if state_path.exists():
        state = load_state(root)
    else:
        # Perder el estado de credenciales no debe provocar rotación sobre una base existente.
        if (local / "postgres_password").exists():
            raise SetupError("Estado incompleto: restaurar evaluation.json; no se reemplaza una credencial existente.")
        state = {"host": "127.0.0.1", "port": 55432, "database": "bia_datos"}
        for name, user in {"superusuario": "postgres", **ROLES}.items():
            state[name] = {"usuario": user, "password": secrets.token_hex(32)}
    # PG_PORT explícito también actualiza instalaciones existentes, sin rotar credenciales.
    try:
        port = int(os.environ.get("PG_PORT", str(state["port"])))
        if not 1024 <= port <= 65535:
            raise ValueError
    except ValueError:
        raise SetupError("PG_PORT debe ser un entero entre 1024 y 65535.") from None
    state["port"] = port
    secret_file = local / "postgres_password"
    password = state["superusuario"]["password"]
    if secret_file.exists() and secret_file.read_text(encoding="utf-8").strip() != password:
        raise SetupError("Credenciales locales inconsistentes; restaurar archivos, no rotar sobre el volumen existente.")
    private_write(state_path, json.dumps(state, indent=2) + "\n")
    private_write(secret_file, password + "\n")
    private_write(local / "compose.env", f"PG_PORT={state['port']}\n")
    application = {k: state[k] for k in ("host", "port", "database")}
    application.update(state["ingesta"])
    private_write(local / "ingesta.json", json.dumps(application, indent=2) + "\n")
    # JSON es un subconjunto válido de YAML; safe_load del verificador lo acepta.
    manifest_path = root / "entrega.yaml"
    candidate = {"nombre_completo": "TODO", "email": "TODO", "horas_invertidas": 0}
    if manifest_path.exists():
        try:
            content = manifest_path.read_text(encoding="utf-8")
            try:
                previous = json.loads(content)
            except ValueError:
                import yaml
                previous = yaml.safe_load(content)
            candidate = previous["candidato"]
            if not isinstance(candidate, dict):
                raise ValueError
            if not all(isinstance(candidate.get(k), str) for k in ("nombre_completo", "email")):
                raise ValueError
            if not isinstance(candidate.get("horas_invertidas"), (int, float)):
                raise ValueError
        except ImportError:
            raise SetupError("Instalar PyYAML para preservar el manifiesto YAML editado.") from None
        except Exception:
            raise SetupError("No se pudo interpretar el manifiesto; no se reemplaza.") from None
    manifest = {
        "candidato": candidate,
        "postgres": {"host": state["host"], "port": state["port"], "database": state["database"],
                     "superusuario": state["superusuario"], "roles": {r: state[r] for r in ROLES}},
        "objetos": {"tabla_consumos": "core.fact_consumo_horario", "tabla_clientes": "core.clientes", "vista_analytics": "analytics.v_consumo_mensual",
                    "tabla_auditoria": "audit.runs"},
        "no_implementado": ["S05-S07 pendientes de autorización e implementación"],
    }
    private_write(manifest_path, json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    return state


def compose(*args: str) -> list[str]:
    return ["docker", "compose", "--project-name", "bia-evaluation", "--env-file",
            str(ROOT / ".local/compose.env"), "-f", str(ROOT / "docker-compose.yml"), *args]


def run_checked(command: list[str], stage: str, *, input_text: str | None = None,
                timeout: int = 180) -> None:
    try:
        result = subprocess.run(command, cwd=ROOT, input=input_text, encoding="utf-8", errors="replace",
                                capture_output=True, timeout=timeout, check=False)
    except (OSError, subprocess.TimeoutExpired):
        raise SetupError(f"{stage}: herramienta no disponible o tiempo agotado.") from None
    if result.returncode:
        # No reenviar stderr: puede contener credenciales o configuración del host.
        raise SetupError(f"{stage}: falló el comando (código {result.returncode}); revisar requisitos del entorno.")


def bootstrap_sql(state: dict) -> str:
    # Solo secretos hexadecimales generados/validados y nombres estáticos, nunca datos de entrada.
    for name in ROLES:
        if not re.fullmatch(r"[a-f0-9]{64}", state[name]["password"]):
            raise SetupError("Formato de credencial inválido.")
    variables = "".join(f"\\set pw_{name} '{state[name]['password']}'\n" for name in ROLES)
    return variables + (ROOT / "sql/001_access.sql").read_text(encoding="utf-8")


def setup() -> None:
    if sys.version_info < (3, 11):
        raise SetupError("Se requiere Python 3.11 o superior.")
    python = ROOT / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
    if not python.exists():
        import venv
        venv.EnvBuilder(with_pip=True).create(ROOT / ".venv")
    run_checked([str(python), "-m", "pip", "install", "--disable-pip-version-check", "--retries", "0",
                 "--timeout", "20", "-r", str(ROOT / "requirements.txt")], "Instalación de dependencias")
    # Ejecutar con el entorno que ya tiene PyYAML para preservar campos humanos.
    run_checked([str(python), str(ROOT / "tools/manage.py"), "prepare"], "Preparación de credenciales")
    print("setup: entorno preparado; credenciales locales generadas o conservadas, sin llave PII.")


def up() -> None:
    state = load_state()
    run_checked(["docker", "compose", "version"], "Comprobación de Docker Compose")
    run_checked(["docker", "info"], "Comprobación del motor Docker")
    run_checked(compose("up", "-d", "--wait", "--wait-timeout", "120"), "Arranque de servicios")
    psql = compose("exec", "-T", "postgres", "psql", "-X", "-q", "-v", "ON_ERROR_STOP=1",
                   "-U", "postgres", "-d", state["database"])
    # Una conexión TCP exige la contraseña incluso si el socket administrativo es confiable.
    # Detecta un volumen antiguo incompatible ANTES de cambiar roles o publicar éxito.
    check_admin = (f"\\setenv PGPASSWORD '{state['superusuario']['password']}'\n"
                   "\\connect bia_datos postgres 127.0.0.1 5432\nSELECT 1;\n")
    run_checked(psql, "Validación de credenciales del volumen", input_text=check_admin)
    run_checked(psql, "Preparación SQL", input_text=bootstrap_sql(state))
    run_checked(psql, "Preparación de privacidad S02",
                input_text=(ROOT / "sql/002_clients.sql").read_text(encoding="utf-8"))
    run_checked(psql, "Preparación de consumos S03",
                input_text=(ROOT / "sql/003_consumptions.sql").read_text(encoding="utf-8"))
    run_checked(psql, "Preparación de facturación y reportes S04",
                input_text=(ROOT / "sql/004_billing.sql").read_text(encoding="utf-8"))
    for name, user in ROLES.items():
        check_role = (f"\\setenv PGPASSWORD '{state[name]['password']}'\n"
                      f"\\connect bia_datos {user} 127.0.0.1 5432\nSELECT current_user;\n")
        run_checked(psql, f"Conexión del rol {name}", input_text=check_role)
    print("up: PostgreSQL y Redpanda disponibles; esquemas, roles y auditoría preparados.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("setup", "prepare", "up", "down", "run", "stream", "clean"))
    args = parser.parse_args()
    try:
        if args.command == "setup":
            setup()
        elif args.command == "prepare":
            prepare()
            print("Credenciales y manifiesto locales preparados; no se generó llave PII.")
        elif args.command == "up":
            up()
        elif args.command == "run":
            return subprocess.run([sys.executable, "-m", "src.batch.pipeline"], cwd=ROOT,
                                  timeout=900, check=False).returncode
        elif args.command == "stream":
            return subprocess.run([sys.executable, "-m", "src.streaming.consumer"], cwd=ROOT,
                                  timeout=280, check=False).returncode
        elif args.command == "down":
            load_state()
            run_checked(compose("down"), "Detención de servicios")
            print("down: servicios detenidos; volúmenes conservados.")
        else:
            raise SetupError(f"{args.command}: pendiente de una fase posterior; no se simula éxito.")
        return 0
    except (SetupError, OSError, subprocess.SubprocessError):
        # OSError puede contener rutas/configuración; no mostrar detalles sin sanear.
        message = str(sys.exception()) if isinstance(sys.exception(), SetupError) else "Error de acceso al entorno local."
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
