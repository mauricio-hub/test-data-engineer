"""T01/T03/T15–T17/T26: seguridad con datos sintéticos, sin PostgreSQL."""
from contextlib import redirect_stdout
import csv
import io
import json
import os
import runpy
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet

from src import client_service, clients, privacy
from src.privacy import Cipher, Classification, PrivacyError, ROOT, SOURCE_COLUMNS, mask_pii


def sample_row(identifier: str = "CLI9001") -> dict[str, str]:
    """Construye un cliente sintético con PII y texto hostil, sin datos personales reales."""
    return dict(zip(SOURCE_COLUMNS, (
        identifier, 'Empresa "Sintética"; DROP TABLE consumos;\n' + 'x' * 200_000,
        '123456789-0', 'persona@example.test', '3001234567', 'Dirección de prueba',
        'Ciudad de prueba', 'Departamento de prueba', 'Persona ficticia',
        'correo persona@example.test; celular +57 300 123 4567; C.C. 12.345.678',
    )))


def csv_bytes(rows: list[dict[str, str]], encoding: str = "utf-8") -> bytes:
    """Serializa clientes sintéticos como CSV completo en la codificación solicitada."""
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(buffer, fieldnames=SOURCE_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue().encode(encoding)


class PrivacyTests(unittest.TestCase):
    """Verifica privacidad, datos hostiles y compatibilidad de las entradas públicas."""
    def setUp(self) -> None:
        """Prepara una llave efímera y la política actual sin escribir secretos operativos."""
        self.key = Fernet.generate_key()  # Llave efímera solo de prueba; nunca se escribe.
        self.cipher = Cipher(self.key)
        self.policy = Classification.load()

    def test_T03_csv_preserves_quotes_multiline_long_text_and_sql(self) -> None:
        """Comprueba que el parser conserva las entradas hostiles sin ejecutar ni truncar texto."""
        row = sample_row()
        for encoding in ("utf-8", "cp1252"):
            with self.subTest(encoding=encoding):
                self.assertEqual(clients.parse_clients(csv_bytes([row], encoding)), [row])

    def test_T03_original_master_has_40_logical_clients(self) -> None:
        """Cuenta clientes del original mediante lectura sin modificar el archivo."""
        self.assertEqual(len(clients.parse_clients((ROOT / "data/maestros/clientes.csv").read_bytes())), 40)

    def test_invalid_csv_ids_and_duplicates_are_explicit(self) -> None:
        """Comprueba que entradas inválidas se rechazan mediante códigos seguros."""
        for data, code in ((b'wrong,header\na,b\n', "csv_invalid"),
                           (csv_bytes([sample_row("invalid")]), "client_id_invalid"),
                           (csv_bytes([sample_row(), sample_row()]), "client_duplicate"),
                           ((','.join(SOURCE_COLUMNS) + '\n"unclosed').encode(), "csv_invalid")):
            with self.subTest(code=code):
                with self.assertRaises(PrivacyError) as caught:
                    clients.parse_clients(data)
                self.assertEqual(caught.exception.code, code)

    def test_T16_masks_email_mobile_and_document_and_counts_clients(self) -> None:
        """Verifica las tres detecciones y el conteo por cliente, no por coincidencia."""
        sanitized, found = mask_pii(sample_row()["observaciones"])
        self.assertTrue(found)
        for sensitive in ('persona@example.test', '300 123 4567', '12.345.678'):
            self.assertNotIn(sensitive, sanitized)
        self.assertEqual(mask_pii('Sin novedades'), ('Sin novedades', False))
        _, found = clients.protect_client(sample_row(), self.policy, self.cipher)
        self.assertIs(found, True)  # Tres detecciones siguen siendo un cliente.

    def test_T17_cipher_is_randomized_authenticated_and_bound_to_context(self) -> None:
        """Verifica aleatoriedad, integridad, contexto y rechazo de una llave distinta."""
        first = self.cipher.seal('synthetic-secret', 'cliente:field')
        second = self.cipher.seal('synthetic-secret', 'cliente:field')
        self.assertNotEqual(first, second)
        self.assertEqual(self.cipher.open(first, 'cliente:field'), 'synthetic-secret')
        for token, context in ((first[:-5] + 'AAAAA', 'cliente:field'), (first, 'other:field')):
            with self.assertRaises(PrivacyError):
                self.cipher.open(token, context)
        with self.assertRaises(PrivacyError):
            Cipher(Fernet.generate_key()).open(first, 'cliente:field')

    def test_T17_all_free_text_is_encrypted_and_observations_are_masked_first(self) -> None:
        """Comprueba el cifrado de textos y el enmascaramiento previo de observaciones."""
        protected, _ = clients.protect_client(sample_row(), self.policy, self.cipher)
        self.assertEqual(protected['cliente_id'], 'CLI9001')
        for column in SOURCE_COLUMNS[1:]:
            self.assertTrue(protected[column].startswith(Cipher.PREFIX))
            value = self.cipher.open(protected[column], f'core.clientes:CLI9001:{column}')
            if column == 'observaciones':
                self.assertNotIn('persona@example.test', value)
                self.assertIn('[EMAIL]', value)
            else:
                self.assertEqual(value, sample_row()[column])

    def test_T15_missing_classification_or_downgrade_fails_closed(self) -> None:
        """Impide escrituras cuando la clasificación es incompleta o debilita la protección."""
        for change in ('missing', 'invalid', 'downgrade'):
            tables = json.loads(json.dumps(self.policy.tables))
            if change == 'missing':
                del tables['core.clientes']['nit']
            else:
                tables['core.clientes']['nit'] = 'unknown' if change == 'invalid' else 'Interno'
            with self.subTest(change=change), self.assertRaises(PrivacyError):
                Classification(tables)
        with self.assertRaises(PrivacyError):
            self.policy.protect('core.clientes', 'unknown', 'synthetic', 'ctx', self.cipher)

    def test_T15_policy_is_consumed_not_only_documented(self) -> None:
        """Comprueba que reclasificar una columna incompatible bloquea la operación."""
        self.assertEqual(self.policy.protect('audit.runs', 'operation', 'test', 'ctx', self.cipher), 'test')
        tables = json.loads(json.dumps(self.policy.tables))
        tables['audit.runs']['operation'] = 'Restringido-PII'
        # Una columna técnica sin formato cifrado compatible no puede guardarse en claro.
        with self.assertRaises(PrivacyError):
            Classification(tables)

    def test_missing_invalid_or_in_repository_key_never_generates_key(self) -> None:
        """Rechaza llaves ausentes, inválidas o internas sin crear una de sustitución."""
        with patch.dict(os.environ):
            os.environ.pop('BIA_PII_KEY_FILE', None)
            with self.assertRaises(PrivacyError) as caught:
                Cipher.from_env()
            self.assertEqual(caught.exception.code, 'key_missing')
        with tempfile.TemporaryDirectory() as directory:
            key_path = Path(directory) / 'secret.key'
            key_path.write_bytes(self.key)
            key_path.chmod(0o600)
            with patch.dict(os.environ, {'BIA_PII_KEY_FILE': str(key_path)}):
                self.assertIsInstance(Cipher.from_env(), Cipher)
                with self.assertRaises(PrivacyError):
                    Cipher.from_env(root=Path(directory))
                key_path.write_bytes(b'bad key')
                with self.assertRaises(PrivacyError):
                    Cipher.from_env()

    def test_T01_T26_logs_and_stdout_do_not_include_driver_errors_or_payloads(self) -> None:
        """Provoca un error con PII sintética y verifica que no llegue a logs ni stdout."""
        sensitive = 'persona@example.test 3001234567 12345678'
        with tempfile.TemporaryDirectory() as directory:
            log_path = Path(directory) / 'pipeline.log'
            output = io.StringIO()
            with patch('src.client_service.Cipher.from_env', return_value=self.cipher), \
                 patch('src.client_service.connect_operational', side_effect=RuntimeError(sensitive)), \
                 redirect_stdout(output):
                self.assertEqual(clients.main(log_path=log_path), 1)
            written = log_path.read_text(encoding='utf-8') + output.getvalue()
            for value in sensitive.split():
                self.assertNotIn(value, written)
            for line in written.splitlines():
                event = json.loads(line)
                self.assertEqual(event['reason'], 'internal_error')
                self.assertNotIn('traceback', event)
            self.assertNotIn(sensitive, str(PrivacyError(sensitive)))


    def test_privacy_facade_preserves_domain_exports(self) -> None:
        """Comprueba que la fachada expone las mismas implementaciones y constantes."""
        from src.security import MESSAGES, PrivacyError as SecurityError
        from src.security.classification import MODEL, SOURCE_COLUMNS as columns, Classification as Policy
        from src.security.encryption import Cipher as Encryptor
        from src.security.masking import BARE_DOCUMENT, DOCUMENT, EMAIL, MOBILE, mask_pii as masker

        for name, expected in {
            "ROOT": ROOT, "MESSAGES": MESSAGES, "PrivacyError": SecurityError,
            "MODEL": MODEL, "SOURCE_COLUMNS": columns, "Classification": Policy,
            "Cipher": Encryptor, "mask_pii": masker, "EMAIL": EMAIL, "MOBILE": MOBILE,
            "DOCUMENT": DOCUMENT, "BARE_DOCUMENT": BARE_DOCUMENT,
        }.items():
            with self.subTest(name=name):
                self.assertIs(getattr(privacy, name), expected)

    def test_clients_facade_delegates_without_duplicate_implementations(self) -> None:
        """Comprueba las funciones públicas y el tipo de resultado de clientes."""
        for name in (
            "ClientResult", "parse_clients", "protect_client", "record_run", "ingest_bytes",
            "connect_operational", "safe_event", "main", "Cipher", "Classification",
            "PrivacyError", "ROOT", "SOURCE_COLUMNS", "mask_pii",
        ):
            with self.subTest(name=name):
                self.assertIs(getattr(clients, name), getattr(client_service, name))

    def test_cli_facade_preserves_exit_code_and_missing_key_guard(self) -> None:
        """Verifica la entrada CLI y que faltar la llave impida abrir PostgreSQL."""
        with patch("src.client_service.main", return_value=1) as delegate:
            with self.assertRaises(SystemExit) as caught:
                runpy.run_path(str(ROOT / "src/clients.py"), run_name="__main__")
            self.assertEqual(caught.exception.code, 1)
            delegate.assert_called_once_with()
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ):
            os.environ.pop("BIA_PII_KEY_FILE", None)
            output = io.StringIO()
            with patch("src.client_service.connect_operational") as connect, redirect_stdout(output):
                self.assertEqual(clients.main(log_path=Path(directory) / "pipeline.log"), 1)
            connect.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["reason"], "key_missing")


if __name__ == '__main__':
    unittest.main()
