"""T02/T20/T31/T33: preparación y fallos seguros, sin servicios externos."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from tools import manage


class SetupTests(unittest.TestCase):
    def test_setup_preserves_manifest_and_does_not_restore_obsolete_status(self) -> None:
        """Comprueba el recorrido setup/prepare sin instalar ni rotar secretos de la instalación."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "repo"
            root.mkdir()
            from cryptography.fernet import Fernet
            key = Path(directory) / "explicit.key"
            key.write_bytes(Fernet.generate_key())
            key.chmod(0o600)
            with patch.dict(os.environ, {"PG_PORT": "55432", "BIA_PII_KEY_FILE": str(key)}):
                original = manage.prepare(root)
                manifest = json.loads((root / "entrega.yaml").read_text(encoding="utf-8"))
                manifest["candidato"] = {"nombre_completo": "Candidato sintético", "email": "example.invalid", "horas_invertidas": 12}
                manifest["objetos"]["vista_analytics"] = "analytics.v_evaluacion"
                manifest["no_implementado"] = [*manage.LEGACY_PENDING, "Limitación sintética declarada"]
                manifest["nota_evaluacion"] = "Conservar"
                (root / "entrega.yaml").write_text(json.dumps(manifest), encoding="utf-8")
                secret = (root / ".local/postgres_password").read_bytes()
                python = root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
                python.parent.mkdir(parents=True)
                python.touch()

                def checked(command: list[str], stage: str, **kwargs: object) -> None:
                    """Ejecuta únicamente prepare en el directorio sintético al delegar setup."""
                    if command[-1] == "prepare":
                        manage.prepare(root)
                    elif command[-1] == "initialize-key":
                        from src.security.keys import initialize_key
                        initialize_key(root)

                with patch.object(manage, "ROOT", root), patch.object(manage, "run_checked", side_effect=checked) as runner, \
                     patch("tools.manage.secrets.token_hex", side_effect=AssertionError("No rotar")):
                    manage.setup()
                    manage.setup()
                self.assertEqual(runner.call_count, 6)
                self.assertEqual([call.args[0][-1] for call in runner.call_args_list][1:3],
                                 ["initialize-key", "prepare"])
                after = json.loads((root / "entrega.yaml").read_text(encoding="utf-8"))
                self.assertEqual(after["no_implementado"], ["Limitación sintética declarada"])
                self.assertEqual(after["objetos"], manifest["objetos"])
                self.assertEqual(after["candidato"], manifest["candidato"])
                self.assertEqual(after["nota_evaluacion"], "Conservar")
                self.assertEqual(after["postgres"], manifest["postgres"])
                self.assertEqual(manage.load_state(root), original)
                self.assertEqual((root / ".local/postgres_password").read_bytes(), secret)

    def test_prepare_is_repeatable_and_manifest_matches(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"PG_PORT": "55439"}):
                first = manage.prepare(root)
            manifest = json.loads((root / "entrega.yaml").read_text(encoding="utf-8"))
            manifest["candidato"]["nombre_completo"] = "Candidato sintético"
            (root / "entrega.yaml").write_text(json.dumps(manifest), encoding="utf-8")
            with patch.dict(os.environ, {"PG_PORT": "55439"}):
                second = manage.prepare(root)
            self.assertEqual(first, second)
            manifest = json.loads((root / "entrega.yaml").read_text(encoding="utf-8"))
            self.assertEqual(manifest["postgres"]["superusuario"], first["superusuario"])
            self.assertEqual(manifest["postgres"]["roles"], {r: first[r] for r in manage.ROLES})
            self.assertEqual(manifest["candidato"]["nombre_completo"], "Candidato sintético")
            self.assertEqual(len({first[r]["password"] for r in ("superusuario", *manage.ROLES)}), 4)
            application = json.loads((root / ".local/ingesta.json").read_text())
            self.assertEqual(application["usuario"], "rol_ingesta")
            self.assertNotIn(first["superusuario"]["password"], json.dumps(application))
            self.assertFalse(any("PII" in p.name for p in (root / ".local").iterdir()))

    def test_inconsistent_secret_fails_without_rotation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manage.prepare(root)
            secret = root / ".local/postgres_password"
            secret.write_text("inconsistent", encoding="utf-8")
            with self.assertRaises(manage.SetupError):
                manage.prepare(root)
            self.assertEqual(secret.read_text(encoding="utf-8"), "inconsistent")

    def test_host_port_change_preserves_credentials_and_other_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.dict(os.environ, {"PG_PORT": "5432"}):
                before = manage.prepare(root)
            secret = (root / ".local/postgres_password").read_bytes()
            with patch.dict(os.environ, {"PG_PORT": "55432"}):
                after = manage.prepare(root)
            expected = dict(before, port=55432)
            self.assertEqual(after, expected)
            self.assertEqual((root / ".local/postgres_password").read_bytes(), secret)
            self.assertEqual((root / ".local/compose.env").read_text(), "PG_PORT=55432\n")
            app = json.loads((root / ".local/ingesta.json").read_text())
            manifest = json.loads((root / "entrega.yaml").read_text(encoding="utf-8"))
            self.assertEqual(app["port"], 55432)
            self.assertEqual(manifest["postgres"]["port"], 55432)
            self.assertEqual(app["password"], before["ingesta"]["password"])
            self.assertEqual(manifest["postgres"]["superusuario"], before["superusuario"])

    def test_new_installation_defaults_to_host_55432(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ):
                os.environ.pop("PG_PORT", None)
                self.assertEqual(manage.prepare(Path(directory))["port"], 55432)

    def test_corrupt_state_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            manage.prepare(root)
            path = root / ".local/evaluation.json"
            path.write_text("{}", encoding="utf-8")
            with self.assertRaises(manage.SetupError):
                manage.prepare(root)
            self.assertEqual(path.read_text(encoding="utf-8"), "{}")

    def test_credentials_cannot_inject_sql(self):
        state = {r: {"password": "not a generated password'"} for r in manage.ROLES}
        with self.assertRaises(manage.SetupError):
            manage.bootstrap_sql(state)

    def test_command_failure_does_not_expose_output(self):
        for outcome in (subprocess.CompletedProcess([], 1, "sensitive", "sensitive"),
                        subprocess.TimeoutExpired([], 1), FileNotFoundError("sensitive")):
            with self.subTest(outcome=type(outcome).__name__):
                with patch("tools.manage.subprocess.run") as runner:
                    if isinstance(outcome, Exception):
                        runner.side_effect = outcome
                    else:
                        runner.return_value = outcome
                    with self.assertRaises(manage.SetupError) as caught:
                        manage.run_checked(["missing-tool"], "test")
                    self.assertNotIn("sensitive", str(caught.exception))

    def test_runtime_has_only_required_dependencies(self):
        lines = (manage.ROOT / "requirements.txt").read_text().splitlines()
        packages = [line.split("==")[0].lower() for line in lines if line and not line.startswith("#")]
        self.assertEqual(set(packages), {"pyyaml", "psycopg2-binary", "cryptography", "kafka-python"})

    def test_redpanda_healthcheck_uses_admin_api_without_watch(self):
        import yaml
        config = yaml.safe_load((manage.ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
        check = config["services"]["redpanda"]["healthcheck"]["test"]
        self.assertEqual(check[:4], ["CMD", "rpk", "cluster", "health"])
        self.assertIn("admin.hosts=127.0.0.1:9644", check)
        self.assertFalse(any("--brokers" in value or value in ("--watch", "--exit-when-healthy") for value in check))
        self.assertIn("127.0.0.1:${PG_PORT:-55432}:5432", config["services"]["postgres"]["ports"])


if __name__ == "__main__":
    unittest.main()
