"""Gestiona los ensayos batch y streaming en el entorno Docker aislado bia-demo."""
from __future__ import annotations

import argparse
from contextlib import contextmanager, closing
import json
from pathlib import Path
import re
import secrets
import subprocess
from time import perf_counter
from typing import Any, Iterator

from src import ROOT
from src.security import PrivacyError
from tools.manage import bootstrap_sql, private_write

HOME = ROOT / ".local/demo"
PORT = 55433
PROJECT = "bia-demo"
VOLUME = "bia-demo_pgdata"
BROKER_PORT = 19092
BROKER_VOLUME = "bia-demo_rpdata"
TABLES = (
    "clientes", "clientes_cuarentena", "fronteras", "limites_frontera",
    "archivos_ingesta", "estado_lectura", "fact_consumo_horario", "consumos_cuarentena",
    "archivos_facturacion", "facturas", "factura_componentes", "facturas_cuarentena",
)


class DemoError(Exception):
    """Informa fallos seguros sin revelar conexiones, datos ni secretos."""


def command(args: list[str], *, input_text: str | None = None) -> str:
    """Ejecuta Docker con salida privada y un límite de tiempo."""
    result = subprocess.run(args, input=input_text, text=True, encoding="utf-8",
                            capture_output=True, timeout=180, check=False)
    if result.returncode:
        raise DemoError("Docker no disponible o comando de demostración fallido.")
    return result.stdout.strip()


def compose(*args: str) -> list[str]:
    """Fija proyecto y archivo exclusivos, sin usar la configuración de evaluación."""
    return ["docker", "compose", "-p", PROJECT, "-f", str(HOME / "compose.json"), *args]


@contextmanager
def exclusive() -> Iterator[None]:
    """Impide ejecutar dos comandos de demostración simultáneamente."""
    HOME.mkdir(parents=True, exist_ok=True)
    lock = HOME / "operation.lock"
    try:
        handle = lock.open("x")
    except FileExistsError:
        raise DemoError("Otra operación demo está activa; no se realizó ningún reinicio.") from None
    try:
        handle.close()
        yield
    finally:
        lock.unlink()


def state(*, existing_only: bool = False) -> dict:
    """Lee credenciales exclusivas; solo las crea si no existe un volumen previo."""
    path = HOME / "state.json"
    if path.exists():
        value = json.loads(path.read_text(encoding="utf-8"))
    else:
        if existing_only:
            raise DemoError("No existe un estado demo preparado; streaming no crea credenciales ni llaves.")
        volumes = command(["docker", "volume", "ls", "--format", "{{.Name}}"])
        if VOLUME in volumes.splitlines() or (HOME / "postgres_password").exists():
            raise DemoError("Estado demo incompleto: restaurarlo; no se sustituyen credenciales.")
        value = {name: {"usuario": user, "password": secrets.token_hex(32)} for name, user in
                 (("superusuario", "postgres"), ("ingesta", "rol_ingesta"),
                  ("analista", "rol_analista"), ("auditor", "rol_auditor"))}
        value["marker"] = secrets.token_hex(32)
        private_write(path, json.dumps(value))
    for name in ("superusuario", "ingesta", "analista", "auditor"):
        if not re.fullmatch(r"[a-f0-9]{64}", value[name]["password"]):
            raise DemoError("Estado demo inválido.")
    if not re.fullmatch(r"[a-f0-9]{64}", value["marker"]):
        raise DemoError("Marcador demo inválido.")
    secret = HOME / "postgres_password"
    password = value["superusuario"]["password"]
    if secret.exists() and secret.read_text().strip() != password:
        raise DemoError("Credenciales demo inconsistentes.")
    if existing_only:
        if not secret.is_file():
            raise DemoError("Estado demo incompleto; no se sustituyen credenciales.")
        return value
    private_write(secret, password + "\n")
    return value


def verify_container(info: dict) -> None:
    """Rechaza contenedores, puertos o volúmenes que no sean exactamente los de ensayo."""
    labels = info["Config"]["Labels"]
    mounts = [m for m in info["Mounts"] if m["Destination"] == "/var/lib/postgresql/data"]
    bindings = info["NetworkSettings"]["Ports"]
    if (labels.get("com.docker.compose.project") != PROJECT
            or labels.get("com.docker.compose.service") != "postgres"
            or bindings != {"5432/tcp": [{"HostIp": "127.0.0.1", "HostPort": str(PORT)}]}
            or len(mounts) != 1 or mounts[0].get("Type") != "volume"
            or mounts[0].get("Name") != VOLUME):
        raise DemoError("Identidad Docker no válida: operación bloqueada.")


def inspect_demo() -> None:
    """Comprueba el contenedor real y la propiedad del volumen antes de conectar."""
    identifier = command(compose("ps", "-q", "postgres"))
    if not identifier or "\n" in identifier:
        raise DemoError("No se encontró un único PostgreSQL demo.")
    verify_container(json.loads(command(["docker", "inspect", identifier]))[0])
    volume = json.loads(command(["docker", "volume", "inspect", VOLUME]))[0]
    if (volume.get("Labels") or {}).get("com.docker.compose.project") != PROJECT:
        raise DemoError("El volumen no pertenece al proyecto demo.")


def inspect_broker(*, required: bool = True) -> None:
    """Verifica identidad y almacenamiento del broker, incluso si ya existe detenido."""
    volumes = command(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if BROKER_VOLUME in volumes.splitlines():
        volume = json.loads(command(["docker", "volume", "inspect", BROKER_VOLUME]))[0]
        labels = volume.get("Labels") or {}
        if (labels.get("com.docker.compose.project") != PROJECT
                or labels.get("com.docker.compose.volume") != "rpdata"):
            raise DemoError("El volumen Redpanda no pertenece a demo; operación bloqueada.")
    identifier = command(["docker", "ps", "-aq", "--filter", f"label=com.docker.compose.project={PROJECT}",
                          "--filter", "label=com.docker.compose.service=redpanda"])
    if not identifier:
        if required:
            raise DemoError("No existe Redpanda demo disponible.")
        return
    if "\n" in identifier:
        raise DemoError("Hay más de un Redpanda demo; operación bloqueada.")
    info = json.loads(command(["docker", "inspect", identifier]))[0]
    labels = info["Config"].get("Labels") or {}
    mounts = [m for m in info["Mounts"] if m["Destination"] == "/var/lib/redpanda/data"]
    binding = [{"HostIp": "127.0.0.1", "HostPort": str(BROKER_PORT)}]
    if (labels.get("com.docker.compose.project") != PROJECT
            or labels.get("com.docker.compose.service") != "redpanda"
            or info["HostConfig"].get("PortBindings") != {"9092/tcp": binding}
            or len(mounts) != 1 or mounts[0].get("Type") != "volume"
            or mounts[0].get("Name") != BROKER_VOLUME
            or BROKER_VOLUME not in volumes.splitlines()):
        raise DemoError("Identidad Redpanda incorrecta; operación bloqueada.")
    if required and (not info["State"]["Running"]
                     or info["NetworkSettings"]["Ports"].get("9092/tcp") != binding):
        raise DemoError("Redpanda demo no está disponible en el puerto aislado.")


def prepare_broker() -> None:
    """Añade y levanta solo Redpanda; no aplica SQL ni reinicia PostgreSQL."""
    inspect_demo()
    inspect_broker(required=False)
    path = HOME / "compose.json"
    document = json.loads(path.read_text(encoding="utf-8"))
    if "postgres" not in document["services"] or document.get("networks"):
        raise DemoError("Configuración demo inesperada; operación bloqueada.")
    document["services"]["redpanda"] = {
        "image": "docker.redpanda.com/redpandadata/redpanda:v26.2.2",
        "command": ["redpanda", "start", "--mode=dev-container", "--smp=1", "--memory=512M",
                    "--reserve-memory=0M", "--node-id=0",
                    "--kafka-addr=internal://0.0.0.0:29092,external://0.0.0.0:9092",
                    f"--advertise-kafka-addr=internal://redpanda:29092,external://127.0.0.1:{BROKER_PORT}"],
        "ports": [f"127.0.0.1:{BROKER_PORT}:9092"],
        "volumes": ["rpdata:/var/lib/redpanda/data"],
        "security_opt": ["no-new-privileges:true"],
        "healthcheck": {"test": ["CMD", "rpk", "cluster", "health", "-X", "admin.hosts=127.0.0.1:9644"],
                        "interval": "3s", "timeout": "10s", "retries": 30, "start_period": "10s"}}
    document["volumes"]["rpdata"] = {"name": BROKER_VOLUME}
    private_write(path, json.dumps(document))
    command(compose("up", "-d", "--no-deps", "--wait", "--wait-timeout", "120", "redpanda"))
    inspect_broker()
    inspect_demo()


def connect(value: dict, *, admin: bool = False) -> Any:
    """Conecta únicamente al puerto fijo de ensayo con sus propias credenciales."""
    import psycopg2
    account = value["superusuario" if admin else "ingesta"]
    return psycopg2.connect(host="127.0.0.1", port=PORT, dbname="bia_datos",
                            user="postgres" if admin else "rol_ingesta",
                            password=account["password"], connect_timeout=5,
                            application_name="bia-demo")


def verify_database(cursor: Any, value: dict) -> None:
    """Exige un marcador privado y el inventario exacto antes de tocar tablas."""
    cursor.execute("SELECT token FROM demo_control.identity WHERE singleton")
    if cursor.fetchall() != [(value["marker"],)]:
        raise DemoError("Marcador de base demo incorrecto.")
    cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='core'")
    if {row[0] for row in cursor.fetchall()} != set(TABLES):
        raise DemoError("Inventario de tablas inesperado; reinicio bloqueado.")


def prepare(value: dict) -> None:
    """Levanta solo PostgreSQL y reutiliza los cuatro scripts SQL de evaluación."""
    volumes = command(["docker", "volume", "ls", "--format", "{{.Name}}"])
    if VOLUME in volumes.splitlines():
        volume = json.loads(command(["docker", "volume", "inspect", VOLUME]))[0]
        if (volume.get("Labels") or {}).get("com.docker.compose.project") != PROJECT:
            raise DemoError("Volumen preexistente ajeno a demo: arranque bloqueado.")
    document = {"services": {"postgres": {
        "image": "postgres:16.15-alpine",
        "environment": {"POSTGRES_DB": "bia_datos", "POSTGRES_USER": "postgres",
                        "POSTGRES_PASSWORD_FILE": "/run/secrets/postgres_password",
                        "POSTGRES_INITDB_ARGS": "--auth-host=scram-sha-256"},
        "ports": [f"127.0.0.1:{PORT}:5432"],
        "volumes": ["pgdata:/var/lib/postgresql/data"],
        "secrets": ["postgres_password"],
        "security_opt": ["no-new-privileges:true"],
        "healthcheck": {"test": ["CMD-SHELL", "pg_isready -U postgres -d bia_datos"],
                        "interval": "2s", "timeout": "3s", "retries": 30}}},
        "volumes": {"pgdata": {"name": VOLUME}},
        "secrets": {"postgres_password": {"file": "postgres_password"}}}
    private_write(HOME / "compose.json", json.dumps(document))
    command(compose("up", "-d", "--wait", "--wait-timeout", "120"))
    inspect_demo()
    # Autenticar por TCP antes de aplicar SQL incluso si existe un volumen previo.
    with closing(connect(value, admin=True)) as connection:
        connection.rollback()
    scripts = bootstrap_sql(value) + "\n" + "\n".join(
        (ROOT / "sql" / name).read_text(encoding="utf-8")
        for name in ("002_clients.sql", "003_consumptions.sql", "004_billing.sql"))
    command(compose("exec", "-T", "postgres", "psql", "-X", "-q", "-v",
                    "ON_ERROR_STOP=1", "-U", "postgres", "-d", "bia_datos"), input_text=scripts)
    with closing(connect(value, admin=True)) as connection:
        with connection.cursor() as cursor:
            cursor.execute("CREATE SCHEMA IF NOT EXISTS demo_control")
            cursor.execute("REVOKE ALL ON SCHEMA demo_control FROM PUBLIC")
            cursor.execute("CREATE TABLE IF NOT EXISTS demo_control.identity ("
                           "singleton boolean PRIMARY KEY CHECK(singleton), token text NOT NULL)")
            cursor.execute("INSERT INTO demo_control.identity VALUES (true,%s) ON CONFLICT DO NOTHING",
                           (value["marker"],))
            verify_database(cursor, value)
        connection.commit()


def reset(connection: Any, value: dict) -> None:
    """Vacía solo las 12 tablas explícitas, con transacción y sin borrar auditoría."""
    with connection:
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout='3s'")
            verify_database(cursor, value)
            # Los nombres son constantes internas. Sin CASCADE: dependencias nuevas bloquean el borrado.
            cursor.execute("TRUNCATE TABLE " + ", ".join("core." + name for name in TABLES))
            for name in TABLES:
                cursor.execute("SELECT count(*) FROM core." + name)
                if cursor.fetchone()[0] != 0:
                    raise DemoError("No se confirmó el vaciado; transacción cancelada.")


def main() -> int:
    """Expone reset confirmado y ejecución batch aislada con mensajes seguros."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("reset", "run", "stream"))
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    started = perf_counter()
    stage = "confirmation"
    try:
        if args.action == "reset" and args.confirm != PROJECT:
            raise DemoError("Requiere: make demo-reset CONFIRM=bia-demo")
        stage = "operation_lock"
        with exclusive():
            if args.action == "reset":
                stage = "key_initialization"
                from src.security.keys import initialize_key
                initialize_key(ROOT, scope="demo")
            stage = "local_state"
            value = state(existing_only=True) if args.action == "stream" else state()
            if args.action == "stream":
                stage = "container_identity"
                inspect_demo()
                stage = "database_connection"
                with closing(connect(value, admin=True)) as admin:
                    with admin.cursor() as cursor:
                        stage = "database_identity"
                        verify_database(cursor, value)
                stage = "broker_preparation"
                prepare_broker()
                stage = "stream"
                from src.streaming.consumer import main as stream_main
                return stream_main(output=HOME / "out", log_path=HOME / "out/pipeline.log",
                                   connection_factory=lambda: connect(value),
                                   bootstrap=f"127.0.0.1:{BROKER_PORT}")
            if args.action == "reset":
                stage = "environment_preparation"
                prepare(value)
                stage = "container_identity"
                inspect_demo()
                stage = "database_connection"
                with closing(connect(value, admin=True)) as connection:
                    stage = "reset"
                    reset(connection, value)
                # Solo salidas conocidas del ensayo; nunca borrar directorios ni originales.
                stage = "report_cleanup"
                for name in ("consumo_mensual.csv", "dq_report.json", "metrics.json"):
                    (HOME / "out" / name).unlink(missing_ok=True)
                result = {"tables_emptied": len(TABLES), "audit_preserved": True}
            else:
                stage = "key_loading"
                from src.batch.pipeline import run_full
                from src.security.encryption import Cipher
                from src.security.classification import Classification
                import yaml
                cipher = Cipher.from_env(scope="demo")
                stage = "container_identity"
                inspect_demo()
                stage = "database_connection"
                with closing(connect(value, admin=True)) as admin:
                    with admin.cursor() as cursor:
                        stage = "database_identity"
                        verify_database(cursor, value)
                stage = "pipeline"
                config = yaml.safe_load((ROOT / "config/pipeline.yaml").read_text(encoding="utf-8"))
                with closing(connect(value)) as connection:
                    result = run_full(connection, ROOT / config["origen"]["ruta"], HOME / "out",
                                      Classification.load(include_billing=True), cipher,
                                      int(config["pipeline"]["batch_size"]))
            event = {"event": "demo_" + args.action, "result": result,
                     "duration_seconds": round(perf_counter() - started, 3)}
            stage = "logging"
            with (HOME / "pipeline.log").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(event) + "\n")
            print(json.dumps(event))
        return 0
    except Exception as error:
        print(json.dumps({"event": "demo_failed", "stage": stage,
                          "reason": error.code if isinstance(error, PrivacyError)
                          else str(error) if isinstance(error, DemoError)
                          else "Operación bloqueada o fallida; no se muestran detalles sensibles."}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
