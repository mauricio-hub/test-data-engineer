-- S03: precedencia persistida, hechos válidos y cuarentena cifrada. No altera datos previos.
BEGIN;
SET LOCAL ROLE bia_owner;

CREATE TABLE IF NOT EXISTS core.fronteras (
    frontera_id text PRIMARY KEY CHECK (frontera_id ~ '^CO[0-9]{10}$'),
    codigo_sic text NOT NULL,
    cliente_id text NOT NULL REFERENCES core.clientes(cliente_id),
    mercado text NOT NULL,
    operador_red text NOT NULL,
    nivel_tension integer NOT NULL,
    fecha_registro date NOT NULL,
    estado text NOT NULL
);
CREATE TABLE IF NOT EXISTS core.limites_frontera (
    frontera_id text PRIMARY KEY REFERENCES core.fronteras(frontera_id),
    min_kwh numeric NOT NULL CHECK (min_kwh >= 0),
    max_kwh numeric NOT NULL CHECK (max_kwh >= min_kwh)
);
CREATE TABLE IF NOT EXISTS core.archivos_ingesta (
    archivo text COLLATE "C" PRIMARY KEY,
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    estado text NOT NULL CHECK (estado IN ('applied','rejected')),
    filas_leidas bigint NOT NULL CHECK (filas_leidas >= 0),
    filas_rechazadas bigint NOT NULL CHECK (filas_rechazadas >= 0)
);
CREATE TABLE IF NOT EXISTS core.estado_lectura (
    frontera_id text NOT NULL REFERENCES core.fronteras(frontera_id),
    timestamp timestamptz NOT NULL,
    version_lectura bigint NOT NULL,
    archivo text COLLATE "C" NOT NULL REFERENCES core.archivos_ingesta(archivo),
    fila bigint NOT NULL CHECK (fila > 0),
    valida boolean NOT NULL,
    PRIMARY KEY (frontera_id, timestamp)
);
CREATE TABLE IF NOT EXISTS core.fact_consumo_horario (
    frontera_id text NOT NULL,
    timestamp timestamptz NOT NULL,
    consumo_kwh numeric NOT NULL CHECK (consumo_kwh >= 0 AND consumo_kwh <= 1000000),
    calidad_lectura text NOT NULL,
    PRIMARY KEY (frontera_id, timestamp),
    FOREIGN KEY (frontera_id, timestamp) REFERENCES core.estado_lectura(frontera_id, timestamp)
);
CREATE TABLE IF NOT EXISTS core.consumos_cuarentena (
    archivo text COLLATE "C" NOT NULL REFERENCES core.archivos_ingesta(archivo),
    source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[a-f0-9]{64}$'),
    fila bigint NOT NULL CHECK (fila >= 0),
    motivo text NOT NULL CHECK (motivo IN ('empty','negative','outlier','invalid_file','changed_file')),
    payload text NOT NULL CHECK (payload LIKE 'fernet:v1:%'),
    PRIMARY KEY (archivo, source_sha256, fila, motivo)
);

REVOKE ALL ON core.fronteras, core.limites_frontera, core.archivos_ingesta,
    core.estado_lectura, core.fact_consumo_horario, core.consumos_cuarentena
    FROM PUBLIC, rol_ingesta, rol_analista, rol_auditor;
GRANT SELECT, INSERT ON core.fronteras, core.limites_frontera, core.archivos_ingesta,
    core.estado_lectura, core.fact_consumo_horario, core.consumos_cuarentena TO rol_ingesta;
GRANT UPDATE (version_lectura, archivo, fila, valida) ON core.estado_lectura TO rol_ingesta;
GRANT UPDATE (consumo_kwh, calidad_lectura) ON core.fact_consumo_horario TO rol_ingesta;
-- A01 necesita retirar exclusivamente el hecho reemplazado por un ganador inválido.
GRANT DELETE ON core.fact_consumo_horario TO rol_ingesta;
COMMIT;
