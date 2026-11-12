"""Tres escenarios S07 de empaquetado, con archivos y ZIP exclusivamente temporales."""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from src import ROOT
from tools import manage
from tools import package_delivery as delivery


class DeliveryTests(unittest.TestCase):
    """Comprueba extracción, exclusiones, límites y secretos sin crear la entrega definitiva."""

    def setUp(self) -> None:
        """Crea una copia temporal del historial real, sin añadir commits ni tocar el repositorio."""
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.root = self.base / "source"
        self.root.mkdir()
        shutil.copytree(ROOT / ".git", self.root / ".git")
        tracked = set(delivery.git(ROOT, "ls-files", "-z").decode("utf-8").split("\0")) - {""}
        for name in (delivery.REQUIRED | tracked) - {".git/HEAD", ".git/config", "entrega.yaml"}:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("fixture\n", encoding="utf-8")
        self.state = manage.prepare(self.root)
        self.destination = self.base / "packages"

    def test_T34_roundtrip_preserves_history_and_excludes_private_files(self) -> None:
        """Extrae ZIP real, verifica Git y demuestra exclusiones a cualquier profundidad."""
        private = ("data/original.csv", ".venv/environment", ".local/private.txt", "logs/pipeline.log",
                   "out/old.json", "infra/.terraform/provider", "infra/state.tfstate.backup",
                   "infra/local.tfvars.json", "src/nested/data/private.csv", "tests/nested/private.key",
                   "src/private.pem", "src/.env.local", "volumes/postgres/data", "node_modules/package",
                   ".git/hooks/untrusted", ".git/logs/private")
        for name in private:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("excluded fixture", encoding="utf-8")
        (self.root / "infra/.terraform.lock.hcl").write_text("# fixture lockfile\n", encoding="utf-8")
        package = delivery.build_package(self.root, self.destination, "candidato_prueba")
        result = delivery.inspect_archive(package, "candidato_prueba")
        self.assertGreater(result["files"], len(delivery.REQUIRED))
        with zipfile.ZipFile(package) as archive:
            names = set(archive.namelist())
            for name in private:
                self.assertNotIn("candidato_prueba/" + name, names)
            self.assertIn("candidato_prueba/entrega.yaml", names)
            self.assertIn("candidato_prueba/config/pipeline.yaml", names)
            tracked = set(delivery.git(self.root, "ls-files", "-z").decode("utf-8").split("\0")) - {""}
            self.assertTrue(all(delivery.excluded(name) or "candidato_prueba/" + name in names
                                for name in tracked))
            self.assertIn("candidato_prueba/infra/.terraform.lock.hcl", names)
            self.assertIn("candidato_prueba/out/", names)
            extracted = self.base / "extracted"
            archive.extractall(extracted)
        restored = extracted / "candidato_prueba"
        self.assertEqual(delivery.git(restored, "rev-parse", "HEAD"), delivery.git(self.root, "rev-parse", "HEAD"))
        delivery.git(restored, "fsck", "--full")
        self.assertEqual((restored / "entrega.yaml").read_bytes(), (self.root / "entrega.yaml").read_bytes())
        self.assertEqual(manage.load_state(self.root), self.state)

    def test_T34_rejects_omitted_tracked_files(self) -> None:
        """Bloquea omisiones de archivos versionados fuera de las rutas permitidas."""
        original_git = delivery.git

        def tracked_with_extra(root: Path, *args: str) -> bytes:
            """Simula un archivo versionado nuevo sin modificar el índice Git."""
            result = original_git(root, *args)
            if args == ("ls-files", "-z"):
                return result + b"additional/runtime.yaml\0"
            return result

        with patch("tools.package_delivery.git", side_effect=tracked_with_extra):
            with self.assertRaisesRegex(delivery.PackageError, "versionados"):
                delivery.build_package(self.root, self.destination, "candidato_prueba")
        self.assertFalse(self.destination.exists())

    def test_T34_rejects_overwrite_traversal_and_linked_sources(self) -> None:
        """Impide destinos peligrosos, sobrescritura, rutas ZIP externas y enlaces de entrada."""
        self.destination.mkdir()
        existing = self.destination / "candidato_prueba.zip"
        existing.write_bytes(b"previous package")
        with self.assertRaises(delivery.PackageError):
            delivery.build_package(self.root, self.destination, "candidato_prueba")
        self.assertEqual(existing.read_bytes(), b"previous package")
        for name in ("../outside", "Candidato_Prueba", "candidato prueba"):
            with self.assertRaises(delivery.PackageError):
                delivery.build_package(self.root, self.destination, name)
        with self.assertRaises(delivery.PackageError):
            delivery.build_package(self.root, self.root / ".git", "candidato_otro")
        malformed = self.base / "malformed.zip"
        with zipfile.ZipFile(malformed, "w") as archive:
            archive.writestr("candidato_prueba/../../outside.txt", "fixture")
        with self.assertRaises(delivery.PackageError):
            delivery.inspect_archive(malformed, "candidato_prueba")
        with patch("tools.package_delivery.linked", return_value=True):
            with self.assertRaises(delivery.PackageError):
                delivery.build_package(self.root, self.destination, "candidato_otro")

    def test_T02_rejects_credentials_in_sources_and_hidden_git_objects(self) -> None:
        """Detecta secretos incluso en blobs Git sin referencia, sin reescribir la historia."""
        leak = self.root / "src/leak.txt"
        leak.parent.mkdir(exist_ok=True)
        leak.write_text(self.state["ingesta"]["password"], encoding="utf-8")
        with self.assertRaises(delivery.PackageError):
            delivery.build_package(self.root, self.destination, "candidato_prueba")
        self.assertFalse(self.destination.exists())
        leak.unlink()  # Solo el fixture creado dentro de TemporaryDirectory.
        private_fixture = b"-----BEGIN " + b"PRIVATE KEY-----\nsynthetic invalid fixture\n"
        result = subprocess.run(["git", "-C", str(self.root), "hash-object", "-w", "--stdin"],
                                input=private_fixture, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0)
        with self.assertRaises(delivery.PackageError):
            delivery.build_package(self.root, self.destination, "candidato_prueba")
        self.assertFalse(self.destination.exists())
