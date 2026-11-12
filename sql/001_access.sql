\set ON_ERROR_STOP on
BEGIN;
SET LOCAL password_encryption = 'scram-sha-256';
-- Roles globales de esta instalación local dedicada; sin pertenencias implícitas.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'bia_owner') THEN
    CREATE ROLE bia_owner NOLOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_ingesta') THEN
    CREATE ROLE rol_ingesta LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_analista') THEN
    CREATE ROLE rol_analista LOGIN;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'rol_auditor') THEN
    CREATE ROLE rol_auditor LOGIN;
  END IF;
END $$;
ALTER ROLE bia_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE rol_ingesta LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE rol_analista LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
ALTER ROLE rol_auditor LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
-- Rechazar pertenencias preexistentes, en lugar de heredar acceso inesperado.
DO $$
BEGIN
  IF EXISTS (
    SELECT FROM pg_auth_members m JOIN pg_roles r ON r.oid = m.member
    WHERE r.rolname IN ('bia_owner','rol_ingesta','rol_analista','rol_auditor')
  ) THEN
    RAISE EXCEPTION 'Roles de evaluación con pertenencias inesperadas';
  END IF;
END $$;
-- Inicializar solo cuentas sin contraseña; nunca rotar credenciales ya existentes.
SELECT format('ALTER ROLE %I PASSWORD %L', 'rol_ingesta', :'pw_ingesta')
  FROM pg_authid WHERE rolname='rol_ingesta' AND rolpassword IS NULL
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', 'rol_analista', :'pw_analista')
  FROM pg_authid WHERE rolname='rol_analista' AND rolpassword IS NULL
\gexec
SELECT format('ALTER ROLE %I PASSWORD %L', 'rol_auditor', :'pw_auditor')
  FROM pg_authid WHERE rolname='rol_auditor' AND rolpassword IS NULL
\gexec
REVOKE ALL ON DATABASE bia_datos FROM PUBLIC;
GRANT CONNECT ON DATABASE bia_datos TO rol_ingesta, rol_analista, rol_auditor;
REVOKE ALL ON SCHEMA public FROM PUBLIC;
CREATE SCHEMA IF NOT EXISTS core AUTHORIZATION bia_owner;
CREATE SCHEMA IF NOT EXISTS analytics AUTHORIZATION bia_owner;
CREATE SCHEMA IF NOT EXISTS audit AUTHORIZATION bia_owner;
ALTER SCHEMA core OWNER TO bia_owner;
ALTER SCHEMA analytics OWNER TO bia_owner;
ALTER SCHEMA audit OWNER TO bia_owner;
REVOKE ALL ON SCHEMA core, analytics, audit FROM PUBLIC, rol_ingesta, rol_analista, rol_auditor;
GRANT USAGE ON SCHEMA core TO rol_ingesta;
GRANT USAGE ON SCHEMA analytics TO rol_analista;
GRANT USAGE ON SCHEMA audit TO rol_ingesta, rol_auditor;

SET LOCAL ROLE bia_owner;
ALTER DEFAULT PRIVILEGES REVOKE EXECUTE ON FUNCTIONS FROM PUBLIC;
CREATE TABLE IF NOT EXISTS audit.runs (
  run_id uuid PRIMARY KEY,
  actor name NOT NULL DEFAULT session_user,
  operation text NOT NULL CHECK (operation IN ('setup','batch','stream','test')),
  recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  rows_read bigint NOT NULL CHECK (rows_read >= 0),
  rows_loaded bigint NOT NULL CHECK (rows_loaded >= 0),
  rows_rejected bigint NOT NULL CHECK (rows_rejected >= 0),
  result text NOT NULL CHECK (result IN ('success','failed','rejected'))
);
-- Sin campos de texto libre ni parámetros para suplantar actor/fecha.
CREATE OR REPLACE FUNCTION audit.record_run(
  p_run_id uuid, p_operation text, p_rows_read bigint, p_rows_loaded bigint,
  p_rows_rejected bigint, p_result text
) RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = pg_catalog
AS $$
  INSERT INTO audit.runs(run_id, actor, operation, rows_read, rows_loaded, rows_rejected, result)
  VALUES (p_run_id, session_user, p_operation, p_rows_read, p_rows_loaded, p_rows_rejected, p_result);
$$;
REVOKE ALL ON audit.runs FROM PUBLIC, rol_ingesta, rol_analista, rol_auditor;
REVOKE ALL ON FUNCTION audit.record_run(uuid,text,bigint,bigint,bigint,text)
  FROM PUBLIC, rol_ingesta, rol_analista, rol_auditor;
GRANT SELECT ON audit.runs TO rol_auditor;
GRANT EXECUTE ON FUNCTION audit.record_run(uuid,text,bigint,bigint,bigint,text) TO rol_ingesta;
-- No se conceden permisos globales sobre futuras tablas de negocio.
-- S02/S03 definirán explícitamente SELECT/INSERT/UPDATE y, si se necesita, DELETE.
COMMIT;
