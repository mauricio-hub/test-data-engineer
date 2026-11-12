"""Integración S02 en una base NUEVA y efímera, nunca en tablas del usuario.

Requiere S01 disponible y permiso administrativo para crear la base de prueba.
BIA_TEST_DB_DRIVER=psycopg permite validar con el driver local de pgAdmin;
por defecto se usa psycopg2, igual que la aplicación.
"""
from contextlib import closing
from contextlib import redirect_stdout
import hashlib
import io
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import uuid
from typing import Any

from cryptography.fernet import Fernet

from src import clients
from src.clients import ingest_bytes
from src.privacy import Cipher, Classification, PrivacyError, ROOT, SOURCE_COLUMNS
from tools import manage
from test_privacy import csv_bytes, sample_row


class PrivacyDatabaseTests(unittest.TestCase):
    """Prueba privacidad y transacciones reales sin cargar las tablas operativas de Bia."""
    @classmethod
    def connect(cls, account: str = "superusuario", *, original: bool = False) -> Any:
        """Abre una conexión al entorno autorizado o a la base temporal de esta suite."""
        user = cls.state[account]
        return cls.driver.connect(host=cls.state['host'], port=cls.state['port'],
                                  dbname=cls.state['database'] if original else cls.database,
                                  user=user['usuario'], password=user['password'], connect_timeout=5)

    @classmethod
    def setUpClass(cls) -> None:
        """Prepara una base propia con el esquema real y una llave exclusiva de prueba."""
        if os.environ.get('BIA_TEST_DB_DRIVER') == 'psycopg':
            import psycopg as driver
            from psycopg import sql
        else:
            import psycopg2 as driver
            from psycopg2 import sql
        cls.driver, cls.sql = driver, sql
        cls.state = manage.load_state()
        cls.database = 'bia_s02_test_' + uuid.uuid4().hex
        cls.cipher = Cipher(Fernet.generate_key())  # Solo fixtures; llave no persistida.
        cls.policy = Classification.load()
        for account in manage.ROLES:
            with closing(cls.connect(account, original=True)):
                pass  # S01 debe estar preparado; no crear/rotar cuentas desde fixtures.
        with closing(cls.connect(original=True)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(cls.database)))
        cls.addClassCleanup(cls.drop_test_database)
        # Mismo DDL de producción, sin metacomandos psql ni cambio de contraseñas globales.
        original = (ROOT / 'sql/001_access.sql').read_text(encoding='utf-8')
        original = re.sub(r"SELECT format\('ALTER ROLE.*?\\gexec", '', original, flags=re.DOTALL)
        lines = original.splitlines()
        initial = '\n'.join(line for line in lines if not line.startswith('\\') and " PASSWORD :'" not in line)
        initial = initial.replace('DATABASE bia_datos', 'DATABASE ' + cls.database)
        with closing(cls.connect()) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(initial)
                cursor.execute((ROOT / 'sql/002_clients.sql').read_text(encoding='utf-8'))
                cursor.execute((ROOT / 'sql/002_clients.sql').read_text(encoding='utf-8'))
                cursor.execute('CREATE TABLE core.s02_consumption_guard(kwh numeric); '
                               'INSERT INTO core.s02_consumption_guard VALUES (42);')

    @classmethod
    def drop_test_database(cls) -> None:
        """Elimina únicamente la base aleatoria creada por esta suite."""
        # Solo el nombre aleatorio que acabamos de crear, compuesto como identificador.
        with closing(cls.connect(original=True)) as connection:
            connection.autocommit = True
            with connection.cursor() as cursor:
                cursor.execute(cls.sql.SQL('DROP DATABASE {}').format(cls.sql.Identifier(cls.database)))

    def query(self, statement: str, parameters: tuple = (), account: str = 'superusuario') -> list:
        """Ejecuta SQL de prueba en la base aislada y devuelve sus filas cuando existen."""
        with closing(self.connect(account)) as connection:
            with connection, connection.cursor() as cursor:
                cursor.execute(statement, parameters)
                return cursor.fetchall() if cursor.description else []

    def load(self, data: bytes, cipher: Cipher | None = None) -> clients.ClientResult:
        """Invoca el servicio real como ingesta dentro de la base temporal."""
        with closing(self.connect('ingesta')) as connection:
            return ingest_bytes(connection, data, self.policy, cipher or self.cipher)

    def test_T03_hostile_text_never_executes_or_truncates(self) -> None:
        """Comprueba que texto hostil se conserva cifrado y no altera la tabla de control."""
        row = sample_row('CLI9001')
        self.load(csv_bytes([row]))
        encrypted = self.query('SELECT razon_social FROM core.clientes WHERE cliente_id=%s', ('CLI9001',))[0][0]
        self.assertEqual(self.cipher.open(encrypted, 'core.clientes:CLI9001:razon_social'), row['razon_social'])
        self.assertEqual(self.query('SELECT kwh FROM core.s02_consumption_guard')[0][0], 42)

    def test_T15_unclassified_database_column_blocks_writes(self) -> None:
        """Comprueba que una columna no clasificada impide modificar clientes."""
        self.query('ALTER TABLE core.clientes ADD COLUMN s02_unclassified text')
        try:
            with self.assertRaises(PrivacyError) as caught:
                self.load(csv_bytes([sample_row('CLI9002')]))
            self.assertEqual(caught.exception.code, 'classification_invalid')
        finally:
            self.query('ALTER TABLE core.clientes DROP COLUMN s02_unclassified')
        self.assertEqual(self.query('SELECT count(*) FROM core.clientes WHERE cliente_id=%s', ('CLI9002',))[0][0], 0)

    def test_T17_ciphertext_at_rest_and_repeat_does_not_change_it(self) -> None:
        """Verifica cifrado como administrador e idempotencia del contenido almacenado."""
        data = csv_bytes([sample_row('CLI9003')])
        first = self.load(data)
        before = self.query('SELECT * FROM core.clientes WHERE cliente_id=%s', ('CLI9003',))
        second = self.load(data)
        after = self.query('SELECT * FROM core.clientes WHERE cliente_id=%s', ('CLI9003',))
        self.assertEqual(first.rows_loaded, 1)
        self.assertEqual(second.rows_loaded, 0)
        self.assertEqual(first.pii_clients, 1)
        self.assertEqual(before, after)
        self.assertTrue(all(value.startswith(Cipher.PREFIX) for value in before[0][1:len(SOURCE_COLUMNS)]))
        self.assertTrue(before[0][len(SOURCE_COLUMNS)])

    def test_T17_invalid_file_is_preserved_only_as_encrypted_quarantine(self) -> None:
        """Verifica conservación cifrada del rechazo sin duplicarlo al reintentar."""
        data = b'wrong,header\npersona@example.test,3001234567\n'
        for _ in range(2):
            with self.assertRaises(PrivacyError):
                self.load(data)
        digest = hashlib.sha256(data).hexdigest()
        rows = self.query('SELECT reason,payload FROM core.clientes_cuarentena WHERE source_sha256=%s', (digest,))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], 'csv_invalid')
        self.assertTrue(rows[0][1].startswith(Cipher.PREFIX))
        import base64
        recovered = self.cipher.open(rows[0][1], f'core.clientes_cuarentena:{digest}:0:csv_invalid')
        self.assertEqual(base64.b64decode(recovered), data)

    def test_T17_wrong_key_cannot_overwrite_existing_rows(self) -> None:
        """Impide sobrescribir datos existentes al usar una llave distinta."""
        self.load(csv_bytes([sample_row('CLI9004')]))
        before = self.query('SELECT * FROM core.clientes WHERE cliente_id=%s', ('CLI9004',))
        with self.assertRaises(PrivacyError) as caught:
            self.load(csv_bytes([sample_row('CLI9004')]), Cipher(Fernet.generate_key()))
        self.assertEqual(caught.exception.code, 'cipher_invalid')
        self.assertEqual(self.query('SELECT * FROM core.clientes WHERE cliente_id=%s', ('CLI9004',)), before)

    def test_T18_analyst_only_sees_technical_ids_and_cannot_write(self) -> None:
        """Verifica acceso mínimo por rol y protección de auditoría con conexiones reales."""
        rows = self.query('SELECT * FROM analytics.v_clientes', account='analista')
        self.assertTrue(all(len(row) == 1 and row[0].startswith('CLI') for row in rows))
        forbidden = (
            ('analista', 'SELECT * FROM core.clientes'),
            ('analista', 'SELECT * FROM core.clientes_cuarentena'),
            ('analista', "INSERT INTO analytics.v_clientes VALUES ('CLI9999')"),
            ('auditor', 'SELECT * FROM core.clientes'),
            ('ingesta', 'TRUNCATE core.clientes'),
            ('ingesta', 'DELETE FROM core.clientes'),
            ('ingesta', "UPDATE core.clientes SET cliente_id='CLI9999'"),
            ('ingesta', 'UPDATE audit.runs SET rows_read=0'),
            ('ingesta', 'DELETE FROM audit.runs'),
            ('ingesta', 'TRUNCATE audit.runs'),
        )
        for account, statement in forbidden:
            with self.subTest(account=account, operation=statement.split()[0]):
                with self.assertRaises(self.driver.Error) as caught:
                    self.query(statement, account=account)
                state = getattr(caught.exception, 'sqlstate', None) or getattr(caught.exception, 'pgcode', None)
                self.assertEqual(state, '42501')

    def test_database_failure_rolls_back_and_cli_does_not_leak_pii(self) -> None:
        """Provoca un fallo SQL y comprueba reversión, auditoría y mensajes sin PII."""
        self.query("""
          CREATE FUNCTION core.s02_reject_fixture() RETURNS trigger LANGUAGE plpgsql AS $$
          BEGIN
            IF NEW.cliente_id='CLI9011' THEN
              RAISE EXCEPTION 'persona@example.test 3001234567 12345678';
            END IF;
            RETURN NEW;
          END $$;
          CREATE TRIGGER s02_reject_fixture BEFORE INSERT ON core.clientes
            FOR EACH ROW EXECUTE FUNCTION core.s02_reject_fixture();
        """)
        try:
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / 'synthetic.csv'
                log = Path(directory) / 'pipeline.log'
                source.write_bytes(csv_bytes([sample_row('CLI9010'), sample_row('CLI9011')]))
                output = io.StringIO()
                with patch('src.client_service.Cipher.from_env', return_value=self.cipher), \
                     patch('src.client_service.connect_operational', side_effect=lambda: self.connect('ingesta')), \
                     redirect_stdout(output):
                    self.assertEqual(clients.main(source=source, log_path=log), 1)
                written = output.getvalue() + log.read_text(encoding='utf-8')
                for secret in ('persona@example.test', '3001234567', '12345678'):
                    self.assertNotIn(secret, written)
                self.assertIn('database_error', written)
            self.assertEqual(self.query("SELECT count(*) FROM core.clientes WHERE cliente_id IN ('CLI9010','CLI9011')")[0][0], 0)
            self.assertGreater(self.query("SELECT count(*) FROM audit.runs WHERE result='failed'")[0][0], 0)
        finally:
            self.query('DROP TRIGGER s02_reject_fixture ON core.clientes; DROP FUNCTION core.s02_reject_fixture()')

    def test_original_master_loads_40_clients_in_isolated_database(self) -> None:
        """Carga el original solo en la base temporal y comprueba las cantidades."""
        data = (ROOT / 'data/maestros/clientes.csv').read_bytes()
        result = self.load(data)
        self.assertEqual(result.rows_read, 40)
        self.assertEqual(result.rows_loaded, 40)
        self.assertEqual(self.query('SELECT count(*) FROM core.clientes WHERE cliente_id LIKE %s', ('CLI00%',))[0][0], 40)
        self.assertEqual(self.query("SELECT count(*) FROM audit.runs WHERE actor='rol_ingesta' AND result='success'")[0][0] > 0, True)


if __name__ == '__main__':
    unittest.main()
