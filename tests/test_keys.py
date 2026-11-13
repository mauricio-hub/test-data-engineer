"""Valida inicialización y recuperación segura con secretos exclusivamente temporales."""
from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from src.security import PrivacyError
from src.security.encryption import Cipher
from src.security import keys


class PortProbeTests(unittest.TestCase):
    """Prueba únicamente la detección del puerto, sin crear llaves ni consultar Docker real."""

    def test_windows_delayed_refusal_uses_five_seconds(self) -> None:
        """Simula el rechazo tardío de Windows que excedía el plazo anterior de un segundo."""
        def delayed_refusal(address: tuple[str, int], *, timeout: float) -> None:
            """Reproduce una respuesta 10061 después de dos segundos sin esperar ni conectar."""
            if timeout < 2:
                raise TimeoutError
            raise ConnectionRefusedError(10061, "Rechazo simulado de Windows")

        with tempfile.TemporaryDirectory() as directory, \
             patch.object(keys, "docker_output", return_value=""), \
             patch.object(keys.socket, "create_connection", side_effect=delayed_refusal) as network, \
             patch.dict(os.environ, {"PG_PORT": "55432"}), \
             patch.object(Fernet, "generate_key", side_effect=AssertionError("No generar llaves")):
            for scope, port in (("evaluation", 55432), ("demo", 55433)):
                with self.subTest(scope=scope):
                    keys.require_fresh_install(Path(directory), scope)
                    network.assert_called_with(("127.0.0.1", port), timeout=5)

    def test_occupied_or_uncertain_port_remains_blocked(self) -> None:
        """Mantiene el bloqueo ante puerto abierto, timeout o error y no crea archivos."""
        from unittest.mock import MagicMock
        with tempfile.TemporaryDirectory() as directory, \
             patch.object(keys, "docker_output", return_value=""), \
             patch.object(keys.socket, "create_connection") as network, \
             patch.object(Fernet, "generate_key", side_effect=AssertionError("No generar llaves")):
            for outcome in (None, TimeoutError("sensitive"), OSError("sensitive")):
                with self.subTest(outcome=type(outcome).__name__):
                    connection = MagicMock()
                    network.return_value = connection
                    network.side_effect = outcome
                    with self.assertRaises(PrivacyError) as caught:
                        keys.require_fresh_install(Path(directory), "demo")
                    self.assertEqual(caught.exception.code, "key_initialization_blocked")
                    self.assertNotIn("sensitive", str(caught.exception))
                    network.assert_called_with(("127.0.0.1", 55433), timeout=5)
                    if outcome is None:
                        connection.close.assert_called_once()
            self.assertEqual(list(Path(directory).iterdir()), [])


class KeyTests(unittest.TestCase):
    """Aísla rutas, entorno y Docker para no crear llaves en la instalación real."""

    def setUp(self) -> None:
        """Prepara un repositorio ficticio y almacenamiento externo temporal."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name)
        self.root = self.base / "repo"
        self.root.mkdir()
        environment = patch.dict(os.environ, {"LOCALAPPDATA": str(self.base / "private"),
                                               "XDG_DATA_HOME": str(self.base / "private")})
        environment.start()
        self.addCleanup(environment.stop)
        os.environ.pop("BIA_PII_KEY_FILE", None)
        docker = patch.object(keys, "docker_output", return_value="")
        self.docker = docker.start()
        self.addCleanup(docker.stop)
        network = patch.object(keys.socket, "create_connection", side_effect=ConnectionRefusedError)
        self.network = network.start()
        self.addCleanup(network.stop)
        # Otra prueba aplica y verifica las ACL reales sobre un directorio temporal vacío.
        self.secure_directory = keys.secure_directory
        security = patch.object(keys, "secure_directory",
                                side_effect=lambda p: p.mkdir(parents=True, mode=0o700, exist_ok=True))
        security.start()
        self.addCleanup(security.stop)

    def test_first_install_and_repeat_preserve_ciphertext(self) -> None:
        """La primera preparación crea; repetir reutiliza sin cambiar llave ni datos."""
        keys.initialize_key(self.root)
        path = keys.key_path()
        original = path.read_bytes()
        cipher = Cipher.from_env(root=self.root)
        ciphertext = cipher.seal("dato sintético", "ctx")
        with patch.object(Fernet, "generate_key", side_effect=AssertionError("No reemplazar")):
            keys.initialize_key(self.root)
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(Cipher.from_env(root=self.root).open(ciphertext, "ctx"), "dato sintético")
        self.assertFalse(path.is_relative_to(self.root))

    def test_setup_initializes_before_credentials_and_reuses_on_second_run(self) -> None:
        """Recorre setup con dependencias simuladas y preparación real solo en archivos temporales."""
        from contextlib import redirect_stdout
        import io
        from tools import manage
        python = self.root / (".venv/Scripts/python.exe" if os.name == "nt" else ".venv/bin/python")
        python.parent.mkdir(parents=True)
        python.touch()

        def checked(command: list[str], stage: str, **kwargs: object) -> None:
            """Simula pip y ejecuta los pasos seguros contra el repositorio ficticio."""
            if command[-1] == "initialize-key":
                keys.initialize_key(self.root)
            elif command[-1] == "prepare":
                manage.prepare(self.root)

        output = io.StringIO()
        with patch.object(manage, "ROOT", self.root), patch.object(manage, "run_checked", side_effect=checked), \
             patch.dict(os.environ, {"PG_PORT": "55432"}), redirect_stdout(output):
            manage.setup()
            first = keys.key_path().read_bytes()
            state = (self.root / ".local/evaluation.json").read_bytes()
            manage.setup()
        self.assertEqual(keys.key_path().read_bytes(), first)
        self.assertEqual((self.root / ".local/evaluation.json").read_bytes(), state)
        self.assertNotIn(first.decode(), output.getvalue())

    def test_explicit_key_has_priority_and_is_never_created(self) -> None:
        """La ruta explícita conserva prioridad, incluso si es inválida o no existe."""
        path = self.base / "explicit.key"
        os.environ["BIA_PII_KEY_FILE"] = str(path)
        with self.assertRaises(PrivacyError):
            keys.initialize_key(self.root)
        self.assertFalse(path.exists())
        original = Fernet.generate_key()
        path.write_bytes(original)
        path.chmod(0o600)
        keys.initialize_key(self.root)
        self.assertEqual(path.read_bytes(), original)
        self.assertIsInstance(Cipher.from_env(root=self.root), Cipher)
        self.docker.assert_not_called()
        path.write_bytes(b"invalid")
        with self.assertRaises(PrivacyError):
            keys.initialize_key(self.root)
        self.assertEqual(path.read_bytes(), b"invalid")

    def test_invalid_default_and_missing_runtime_never_generate(self) -> None:
        """Los comandos lectores fallan sin crear; setup no repara archivos inválidos."""
        with patch.object(Fernet, "generate_key", side_effect=AssertionError("No generar")):
            with self.assertRaises(PrivacyError) as caught:
                Cipher.from_env(root=self.root)
            self.assertEqual(caught.exception.code, "key_missing")
            path = keys.key_path()
            path.parent.mkdir(parents=True)
            path.write_bytes(b"invalid")
            with self.assertRaises(PrivacyError):
                keys.initialize_key(self.root)
            self.assertEqual(path.read_bytes(), b"invalid")

    def test_missing_key_with_local_history_blocks_generation(self) -> None:
        """Conserva datos previos y rechaza generar una llave incompatible."""
        local = self.root / ".local"
        local.mkdir()
        previous = Fernet(Fernet.generate_key()).encrypt(b"synthetic")
        (local / "evaluation.json").write_bytes(previous)
        with patch.object(Fernet, "generate_key", side_effect=AssertionError("No generar")):
            with self.assertRaises(PrivacyError) as caught:
                keys.initialize_key(self.root)
        self.assertEqual(caught.exception.code, "key_initialization_blocked")
        self.assertEqual((local / "evaluation.json").read_bytes(), previous)
        self.assertFalse(keys.key_path().exists())
        self.docker.assert_not_called()

    def test_existing_docker_or_unavailable_docker_blocks_generation(self) -> None:
        """Un clon limpio tampoco puede generar sobre un volumen anterior o incierto."""
        for results in (("bia-evaluation_pgdata\n", "", ""), ("", "other_volume\n", ""),
                        ("", "", "existing_container\n")):
            with self.subTest(results=results):
                self.docker.side_effect = list(results)
                with self.assertRaises(PrivacyError):
                    keys.initialize_key(self.root)
                self.assertFalse(keys.key_path().exists())
        self.docker.side_effect = OSError("synthetic sensitive error")
        with self.assertRaises(PrivacyError) as caught:
            keys.initialize_key(self.root)
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertFalse(keys.key_path().exists())

    def test_demo_default_is_independent_and_cannot_replace_main_key(self) -> None:
        """Demo ignora el estado principal y tiene una llave distinta; su pérdida bloquea."""
        keys.initialize_key(self.root)
        main = keys.key_path().read_bytes()
        (self.root / ".local").mkdir()
        (self.root / ".local/evaluation.json").write_text("existing")
        self.docker.side_effect = ["bia-evaluation_pgdata\n", "", ""]
        keys.initialize_key(self.root, "demo")
        demo_path = keys.key_path("demo")
        self.assertNotEqual(demo_path.read_bytes(), main)
        self.assertEqual(keys.key_path().read_bytes(), main)
        demo_path.unlink()  # Solo fixture temporal, nunca la llave de la instalación.
        (self.root / ".local/demo").mkdir()
        (self.root / ".local/demo/state.json").write_text("existing")
        with self.assertRaises(PrivacyError):
            keys.initialize_key(self.root, "demo")
        self.assertFalse(demo_path.exists())
        self.assertEqual(keys.key_path().read_bytes(), main)

    def test_wrong_key_cannot_decrypt_existing_data(self) -> None:
        """Una llave distinta no recupera ciphertext; ninguna función modifica el original."""
        ciphertext = Cipher(Fernet.generate_key()).seal("sintético", "ctx")
        keys.initialize_key(self.root)
        with self.assertRaises(PrivacyError) as caught:
            Cipher.from_env(root=self.root).open(ciphertext, "ctx")
        self.assertEqual(caught.exception.code, "cipher_invalid")

    def test_existing_unmanaged_server_blocks_generation(self) -> None:
        """Un servidor en el puerto esperado bloquea incluso sin etiquetas ni estado local."""
        from unittest.mock import MagicMock
        connection = MagicMock()
        self.network.side_effect = None
        self.network.return_value = connection
        with self.assertRaises(PrivacyError):
            keys.initialize_key(self.root)
        connection.close.assert_called_once()
        self.assertFalse(keys.key_path().exists())

    def test_directory_permissions_are_private(self) -> None:
        """Aplica y verifica permisos reales únicamente sobre un directorio temporal vacío."""
        import subprocess
        path = self.base / "acl-test"
        self.secure_directory(path)
        if os.name != "nt":
            self.assertEqual(path.stat().st_mode & 0o777, 0o700)
        else:
            script = ("$a=Get-Acl -LiteralPath $env:BIA_KEY_DIRECTORY; "
                      "$s=[System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value; "
                      "if (-not $a.AreAccessRulesProtected -or $a.Access.Count -ne 1) {exit 1}; "
                      "if ($a.Access[0].IdentityReference.Translate("
                      "[System.Security.Principal.SecurityIdentifier]).Value -ne $s) {exit 1}")
            result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                    env=dict(os.environ, BIA_KEY_DIRECTORY=str(path)),
                                    capture_output=True, timeout=15, check=False)
            self.assertEqual(result.returncode, 0)
