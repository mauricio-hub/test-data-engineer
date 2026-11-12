BEGIN;
SET LOCAL ROLE bia_owner;
-- Textos sin límite artificial: nunca truncar entradas hostiles.
-- La aplicación entrega ciphertext; PostgreSQL no recibe la llave.
CREATE TABLE IF NOT EXISTS core.clientes (
  cliente_id text PRIMARY KEY CHECK (cliente_id ~ '^CLI[0-9]{4}$'),
  razon_social text NOT NULL,
  nit text NOT NULL,
  email_contacto text NOT NULL,
  celular_contacto text NOT NULL,
  direccion text NOT NULL,
  ciudad text NOT NULL,
  departamento text NOT NULL,
  representante_legal text NOT NULL,
  observaciones text NOT NULL,
  observaciones_con_pii boolean NOT NULL,
  source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
  CHECK (
    razon_social LIKE 'fernet:v1:%' AND nit LIKE 'fernet:v1:%'
    AND email_contacto LIKE 'fernet:v1:%' AND celular_contacto LIKE 'fernet:v1:%'
    AND direccion LIKE 'fernet:v1:%' AND ciudad LIKE 'fernet:v1:%'
    AND departamento LIKE 'fernet:v1:%' AND representante_legal LIKE 'fernet:v1:%'
    AND observaciones LIKE 'fernet:v1:%'
  )
);
CREATE TABLE IF NOT EXISTS core.clientes_cuarentena (
  source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
  record_number integer NOT NULL CHECK (record_number >= 0),
  reason text NOT NULL CHECK (reason IN ('csv_invalid','client_id_invalid','client_duplicate')),
  payload text NOT NULL CHECK (payload LIKE 'fernet:v1:%'),
  PRIMARY KEY (source_sha256, record_number, reason)
);
CREATE OR REPLACE VIEW analytics.v_clientes AS SELECT cliente_id FROM core.clientes;
REVOKE ALL ON core.clientes, core.clientes_cuarentena, analytics.v_clientes
  FROM PUBLIC, rol_ingesta, rol_analista, rol_auditor;
GRANT SELECT, INSERT ON core.clientes TO rol_ingesta;
GRANT UPDATE (razon_social, nit, email_contacto, celular_contacto, direccion, ciudad,
              departamento, representante_legal, observaciones, observaciones_con_pii, source_sha256)
  ON core.clientes TO rol_ingesta;
GRANT SELECT, INSERT ON core.clientes_cuarentena TO rol_ingesta;
GRANT SELECT ON analytics.v_clientes TO rol_analista;
COMMIT;
