-- S04: facturas sin PII en claro, componentes, cuarentena y vista analítica.
BEGIN;
SET LOCAL ROLE bia_owner;
CREATE TABLE IF NOT EXISTS core.archivos_facturacion (
    archivo text PRIMARY KEY,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    estado text NOT NULL CHECK (estado IN ('applied','rejected')),
    filas_leidas bigint NOT NULL CHECK (filas_leidas >= 0),
    filas_rechazadas bigint NOT NULL CHECK (filas_rechazadas >= 0)
);
CREATE TABLE IF NOT EXISTS core.facturas (
    factura_id text PRIMARY KEY,
    frontera_id text NOT NULL REFERENCES core.fronteras(frontera_id),
    periodo date NOT NULL CHECK (EXTRACT(DAY FROM periodo)=1),
    consumo_facturado_kwh numeric NOT NULL,
    tarifa_cop_kwh numeric NOT NULL,
    valor_total_cop numeric NOT NULL,
    archivo text NOT NULL REFERENCES core.archivos_facturacion(archivo),
    payload text NOT NULL CHECK (payload LIKE 'fernet:v1:%')
);
CREATE TABLE IF NOT EXISTS core.factura_componentes (
    factura_id text NOT NULL REFERENCES core.facturas(factura_id),
    posicion integer NOT NULL CHECK (posicion > 0),
    valor_cop_kwh numeric NOT NULL,
    payload text NOT NULL CHECK (payload LIKE 'fernet:v1:%'),
    PRIMARY KEY (factura_id,posicion)
);
CREATE TABLE IF NOT EXISTS core.facturas_cuarentena (
    archivo text NOT NULL REFERENCES core.archivos_facturacion(archivo),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    fila bigint NOT NULL CHECK (fila >= 0),
    motivo text NOT NULL CHECK (motivo IN ('orphan_invoice','invalid_file','changed_file')),
    payload text NOT NULL CHECK (payload LIKE 'fernet:v1:%'),
    PRIMARY KEY (archivo,source_sha256,fila,motivo)
);
CREATE OR REPLACE VIEW analytics.v_consumo_mensual AS
SELECT frontera_id,
       to_char(timestamp AT TIME ZONE 'America/Bogota','YYYY-MM') AS mes,
       sum(consumo_kwh) AS consumo_kwh,
       count(*) AS horas_con_dato
FROM core.fact_consumo_horario
GROUP BY frontera_id,to_char(timestamp AT TIME ZONE 'America/Bogota','YYYY-MM');

REVOKE ALL ON core.archivos_facturacion,core.facturas,core.factura_componentes,
    core.facturas_cuarentena,analytics.v_consumo_mensual
    FROM PUBLIC,rol_ingesta,rol_analista,rol_auditor;
GRANT SELECT,INSERT ON core.archivos_facturacion,core.facturas,
    core.factura_componentes,core.facturas_cuarentena TO rol_ingesta;
GRANT USAGE ON SCHEMA analytics TO rol_ingesta;
GRANT SELECT ON analytics.v_consumo_mensual TO rol_ingesta,rol_analista;
COMMIT;
