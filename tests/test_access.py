"""T18/T19/T33: permisos reales. Sin PostgreSQL accesible estas pruebas FALLAN.

Por defecto usa psql del contenedor. S01_PSQL permite comprobar el mismo SQL
con un psql local contra un servidor aislado; no sustituye verificar Compose.
"""
import os
from pathlib import Path
import subprocess
import unittest
import uuid

from tools import manage


class AccessTests(unittest.TestCase):
    @classmethod
    def query(cls, account, statement):
        credentials = cls.state[account]
        local = os.environ.get("S01_PSQL")
        if local:
            command = [local, "-h", cls.state["host"], "-p", str(cls.state["port"])]
        else:
            command = manage.compose("exec", "-T", "--env", "PGPASSWORD", "postgres", "psql",
                                     "-h", "127.0.0.1", "-p", "5432")
        command += ["-X", "-q", "-t", "-A", "-v", "ON_ERROR_STOP=1", "-v", "VERBOSITY=sqlstate",
                    "-U", credentials["usuario"], "-d", cls.state["database"]]
        environment = os.environ.copy()
        environment["PGPASSWORD"] = credentials["password"]
        try:
            result = subprocess.run(command, input=statement, encoding="utf-8", errors="replace", capture_output=True,
                                    cwd=manage.ROOT, env=environment, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired):
            raise AssertionError("PostgreSQL/psql no disponible; integración no verificada.") from None
        # Solo SQLSTATE en errores; nunca reenviar mensajes, SQL ni secretos.
        return result.returncode, result.stdout.strip(), result.stderr

    @classmethod
    def successful(cls, account, statement):
        code, output, _ = cls.query(account, statement)
        if code:
            raise AssertionError(f"Operación esperada falló para {account}; código {code}.")
        return output

    def denied(self, account, statement):
        code, _, error = self.query(account, statement)
        self.assertNotEqual(code, 0, f"Operación prohibida permitida para {account}")
        self.assertIn("42501", error, "Se esperaba permiso denegado, no un fallo de conexión/sintaxis")

    @classmethod
    def setUpClass(cls):
        cls.state = manage.load_state()
        cls.successful("superusuario", "SELECT 1;")
        cls.successful("superusuario", manage.bootstrap_sql(cls.state))
        fingerprint_query = ("SELECT md5(string_agg(rolpassword,',' ORDER BY rolname)) FROM pg_authid "
                             "WHERE rolname IN ('rol_ingesta','rol_analista','rol_auditor');")
        before = cls.successful("superusuario", fingerprint_query)
        cls.successful("superusuario", manage.bootstrap_sql(cls.state))
        if cls.successful("superusuario", fingerprint_query) != before:
            raise AssertionError("Repetir la preparación no debe rotar contraseñas ya inicializadas.")
        suffix = uuid.uuid4().hex
        cls.table = f"core.s01_probe_{suffix}"
        cls.view = f"analytics.s01_probe_{suffix}"
        cls.run_id = str(uuid.uuid4())
        # Objetos sintéticos de prueba, no modelo definitivo ni datos originales.
        cls.successful("superusuario", f"""
          SET ROLE bia_owner;
          CREATE TABLE {cls.table}(id integer PRIMARY KEY, kwh numeric, pii bytea);
          GRANT SELECT(id,kwh), INSERT(id,kwh), UPDATE(kwh) ON {cls.table} TO rol_ingesta;
          CREATE VIEW {cls.view} AS SELECT id,kwh FROM {cls.table};
          GRANT SELECT ON {cls.view} TO rol_analista;
        """)

    @classmethod
    def tearDownClass(cls):
        cls.successful("superusuario", f"""
          DROP VIEW {cls.view}; DROP TABLE {cls.table};
          DELETE FROM audit.runs WHERE run_id = '{cls.run_id}';
        """)

    def test_T33_real_connections(self):
        for account in ("superusuario", *manage.ROLES):
            self.assertEqual(self.successful(account, "SELECT current_user;"), self.state[account]["usuario"])

    def test_T18_roles_have_no_administrative_privileges(self):
        self.assertEqual(self.successful("superusuario", """
          SELECT count(*) FROM pg_roles WHERE rolname IN
            ('bia_owner','rol_ingesta','rol_analista','rol_auditor')
          AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls);
        """), "0")
        self.assertEqual(self.successful("superusuario",
            "SELECT rolcanlogin FROM pg_roles WHERE rolname='bia_owner';"), "f")
        for account in manage.ROLES:
            for sql in ("SET ROLE bia_owner;", "CREATE ROLE s01_forbidden;", "CREATE SCHEMA s01_forbidden;",
                        "CREATE TEMP TABLE s01_forbidden(id int);",
                        f"ALTER TABLE {self.table} ADD COLUMN forbidden int;",
                        f"GRANT SELECT ON {self.table} TO PUBLIC;"):
                with self.subTest(account=account, operation=sql.split()[0]):
                    self.denied(account, sql)

    def test_T18_business_update_is_separate_from_audit(self):
        self.successful("ingesta", f"INSERT INTO {self.table}(id,kwh) VALUES(1,100);")
        self.successful("ingesta", f"UPDATE {self.table} SET kwh=110 WHERE id=1;")
        self.assertEqual(self.successful("analista", f"SELECT kwh FROM {self.view} WHERE id=1;"), "110")
        self.denied("ingesta", f"SELECT pii FROM {self.table};")
        self.denied("ingesta", f"DELETE FROM {self.table};")
        self.denied("ingesta", f"TRUNCATE {self.table};")
        for account in ("analista", "auditor"):
            self.denied(account, f"SELECT * FROM {self.table};")
            self.denied(account, f"INSERT INTO {self.table}(id,kwh) VALUES(2,1);")
            self.denied(account, f"UPDATE {self.table} SET kwh=0;")
            self.denied(account, f"DELETE FROM {self.table};")
        self.denied("analista", f"INSERT INTO {self.view}(id,kwh) VALUES(2,1);")
        self.denied("auditor", f"SELECT * FROM {self.view};")

    def test_T19_audit_is_insert_only_via_function(self):
        self.successful("ingesta", f"SELECT audit.record_run('{self.run_id}','test',2,1,1,'success');")
        self.assertEqual(self.successful("auditor", f"""
          SELECT actor||'|'||operation||'|'||rows_read||'|'||rows_loaded||'|'||rows_rejected||'|'||result
          FROM audit.runs WHERE run_id='{self.run_id}' AND recorded_at IS NOT NULL;
        """), "rol_ingesta|test|2|1|1|success")
        for account in manage.ROLES:
            for statement in ("UPDATE audit.runs SET rows_read=0;", "DELETE FROM audit.runs;",
                              "TRUNCATE audit.runs;", "ALTER TABLE audit.runs ADD COLUMN forbidden int;",
                              "INSERT INTO audit.runs DEFAULT VALUES;"):
                with self.subTest(account=account, operation=statement.split()[0]):
                    self.denied(account, statement)
        for account in ("ingesta", "analista"):
            self.denied(account, "SELECT * FROM audit.runs;")
        for account in ("analista", "auditor"):
            self.denied(account, f"SELECT audit.record_run('{uuid.uuid4()}','test',0,0,0,'success');")
        code, _, error = self.query("ingesta",
            f"SELECT audit.record_run('{uuid.uuid4()}','free text',0,0,0,'success');")
        self.assertNotEqual(code, 0)
        self.assertIn("23514", error, "El registro no debe admitir operaciones de texto libre")


if __name__ == "__main__":
    unittest.main()
