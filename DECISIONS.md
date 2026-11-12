# Decisiones iniciales de arquitectura

Actualización S04: alcance reducido e interpretaciones A01–A06 aprobados por el usuario; implementación y pruebas aisladas realizadas. Los estados de fases previas conservan su contexto histórico. Contrato Make local pendiente de validación del operador.

Fecha inicial: 2026-11-10. Arquitectura general y S01–S03 autorizados. Ingesta de consumos implementada; reportes y contrato completo siguen pendientes de S04. Ver `specs/AMBIGUITIES.md`.

## ADR-001 — ETL local con Python y agregación SQL
**Estado:** propuesta dentro de arquitectura general aprobada.
**Contexto:** entradas heterogéneas y PII que no debe quedar en claro en base.
**Opciones:** ETL en Python; ELT con carga cruda en PostgreSQL; motor distribuido.
**Propuesta:** parsear, normalizar y proteger antes de cargar; agregar con SQL. Archivos originales siguen como origen inmutable; no usar MinIO local sin necesidad.
**Razón y consecuencias:** reduce copias de PII y servicios; se renuncia a una capa raw SQL y a procesamiento distribuido innecesario para el volumen.

## ADR-002 — Modelo relacional pequeño con hechos horarios
**Estado:** clientes, cuarentena y vista de identificadores implementados en S02; fronteras, límites y consumos en S03. Facturación y vista analítica definitiva pendientes de S04.
**Contexto:** consumo horario, maestros y facturas anidadas.
**Opciones:** JSON crudo; tabla plana única; dimensiones y hechos relacionados.
**Propuesta:** clientes/fronteras/límites, consumo único por frontera-hora, factura y componentes separados; vista analítica sin PII.
**Razón y consecuencias:** integridad y agregación claras, sin duplicación por componentes. Más tablas que una única tabla plana; no introducir historial dimensional sin requisito.

## ADR-003 — Precedencia persistida y transacción por archivo
**Estado:** precedencia y transacciones aprobadas e implementadas en S03. A01 aprobada internamente; contadores de calidad y calendario pendientes de S04.
**Contexto:** correcciones, empates y archivos corruptos sin regresión.
**Opciones:** recargar todo; sobrescribir por llegada; comparar precedencia persistida.
**Propuesta:** versión + nombre lexicográfico + posición lógica; hash de contenido y transacción por archivo. No actualizar filas sin cambio.
**Razón y consecuencias:** aplica correcciones incrementales y aísla corrupción. Requiere metadatos y semántica explícita de métricas. Contenido distinto bajo igual nombre se rechaza, conservando lo aplicado.

## ADR-004 — Cifrado autenticado en aplicación
**Estado:** implementada en S02; validación con dependencias fijadas pendiente de instalación.
**Contexto:** el evaluador consulta tablas como superusuario.
**Opciones:** cifrado de disco; pgcrypto con llaves accesibles a base; cifrado en aplicación.
**Propuesta:** cifrar Restringido-PII antes de SQL; llave externa a base/paquete, clasificación activa, joins por identificadores técnicos.
**Razón y consecuencias:** dump no expone texto claro. Compromiso del proceso con llave sigue siendo riesgo; requiere custodia de llave y no permite buscar directamente por ciphertext aleatorio.

**Concreción S02:** Fernet de `cryptography` (cifrado autenticado), prefijo `fernet:v1:` y contexto de cliente/columna dentro del mensaje autenticado para impedir intercambios de ciphertext. Todos los textos del maestro se cifran, incluidas observaciones previamente enmascaradas. Los datos originales permanecen intactos. La llave se lee solo desde `BIA_PII_KEY_FILE`, fuera del repositorio; falta/llave incorrecta implica fallo. No se implementa rotación automática; cambiar la llave exige una migración posterior explícita. Enmascaramiento heurístico conservador: no se promete detectar toda PII imaginable, por eso el texto libre no se publica.

## ADR-005 — Propiedad separada y roles operativos mínimos
**Estado:** auditoría y permisos de clientes implementados en S01/S02; permisos de consumos en S03, probados con conexiones reales. Validación con Compose pendiente.
**Contexto:** roles evaluados mediante operaciones prohibidas y auditoría append-only.
**Opciones:** aplicación superusuario; roles propietarios; propietario sin login y grants específicos.
**Decisión:** preparación administrativa separada; ingesta, analista y auditor sin propiedad ni escalamiento. Auditoría insertable mediante `audit.record_run`, con actor obtenido de la sesión, sin modificación/borrado/truncado por roles operativos. En negocio podrán concederse permisos específicos de actualización para correcciones; no se aplica una prohibición global de UPDATE/DELETE/TRUNCATE a todas las tablas.
**Razón y consecuencias:** permisos exigibles por PostgreSQL; requiere bootstrap y tests negativos. Superusuario conserva poderes administrativos: no prometer inmutabilidad frente a él.

**Configuración S01:** `make setup` instala en `.venv/` y genera contraseñas aleatorias nuevas para cada instalación, reutilizadas al reejecutar. `.local/evaluation.json` es administrativo; `.local/ingesta.json` solo contiene la cuenta operativa. `entrega.yaml` se genera para evaluación y no se versiona. La llave PII no se genera: S02 exige un archivo externo explícito. Un volumen con contraseña incompatible debe producir error antes de aplicar permisos; los roles con contraseña existente no se rotan.

## ADR-006 — Replay Kafka acotado por offsets
**Estado:** propuesta; cierre y ausencia bloqueados por A07/A08.
**Contexto:** consumidor real con límite de 300 s y archivo finito, sin conteo fijo.
**Opciones:** consumidor infinito; timeout de inactividad; rango de offsets del replay confirmado.
**Propuesta:** consumir rango por partición, evaluar retroactividad en orden de llegada y ausencia final en rejilla si se aprueba A07.
**Razón y consecuencias:** terminación verificable y aislamiento de replays previos; ausencia se conoce al cierre, no en tiempo real. Exige revisar política si el evaluador espera emisión online.

## ADR-007 — Separación modular de S02 con fachadas compatibles
**Estado:** aprobada por el usuario e implementada para S02; no autoriza S03.
**Contexto:** privacidad y clientes concentraban seguridad, persistencia y observabilidad en dos archivos. Había que separar responsabilidades sin cambiar contratos ni adelantar ETL.
**Opciones:** mantener ambos archivos concentrados; crear batch/calidad en S02; separar únicamente seguridad, servicio de clientes y observabilidad.
**Decisión:** tercera opción. `src/security/` contiene errores, cifrado, clasificación y máscaras; `src/client_service.py` conserva el flujo existente; `src/observability.py` recibe campos simples y llamadas de auditoría. `src/privacy.py` y `src/clients.py` mantienen imports y CLI como fachadas, sin algoritmos duplicados.
**Razón y consecuencias:** evita ciclos y conserva la interfaz existente. El servicio aún contiene la lectura/persistencia específica de clientes; extraer ETL común corresponde a S03. No se cambian esquema, permisos, formato Fernet, política, dependencias o puertos.
**Verificación:** 31 pruebas existentes aprobadas antes y después con PostgreSQL real y psql local, más tres pruebas nuevas de compatibilidad. Cuerpos trasladados, firmas de llamada, tokens y eventos conservados. Docker permanece bloqueado en este entorno.

### Concreción S03 aprobada — plan reducido

- Sin trasladar funciones de `client_service.py` ni cambiar fachadas/pruebas S02. Separación básica entre extracción, transformación y persistencia, sin validadores adicionales.
- `core.fronteras` y `core.limites_frontera` referencian clientes y fronteras; maestros existentes no se sobrescriben. `core.archivos_ingesta` identifica por nombre y hash: nombres distintos participan en B3 aunque repitan contenido.
- `core.estado_lectura` conserva clave frontera/hora y precedencia; `core.fact_consumo_horario` guarda únicamente lecturas válidas con esa clave referenciada. NUMERIC sin escala impuesta evita redondear antes de S04.
- **A01:** el ganador inválido mantiene precedencia y retira solo el hecho de esa hora. Cada rechazo B4 va a `core.consumos_cuarentena`; corrupción estructural conserva el archivo completo cifrado. No recuperar una versión inferior.
- Ingesta recibe UPDATE solo sobre columnas de precedencia/hechos y DELETE únicamente sobre hechos horarios para A01. Archivos y cuarentena reciben SELECT/INSERT; auditoría conserva sus restricciones S01.
- Transacción por archivo y bloqueo transaccional de aplicación para serializar escritores S03. Los archivos confirmados permanecen ante un fallo posterior; reintentar no los duplica. Fallos auditados tras rollback cuando la conexión lo permite.
- Clientes conserva validación S02 por defecto; batch verifica las columnas nuevas contra clasificación. No se reimplementa cifrado ni conexión.
- Colombia mediante UTC−5 fijo, equivalente a `America/Bogota` para las fechas de la prueba, sin nueva dependencia en Windows.
- Negocio y cuarentena estables al reejecutar; auditoría y logs cambian por intento. Reportes, contadores de calidad, facturación, métricas contractuales y conexión de `make run` siguen en S04. No se certifica aún el contrato completo.

## ADR-008 — Facturación protegida y publicación reproducible

**Estado:** aprobada e implementada en S04; probada con PostgreSQL real en base propia temporal. GNU Make y llave operativa no disponibles en este entorno.

**Decisión:** conservar el servicio de clientes y `run` S03; añadir `run_full` para facturación, contexto SQL y reportes. Modelo: archivos de facturación, facturas con frontera referenciada, componentes por posición y cuarentena. Los datos privados de emisor/cliente/pago y los conceptos se cifran antes de SQL; evitar copiar datos de clientes en columnas claras. Analista consulta vista mensual, sin acceso a tablas base. Preparación añade SQL 004 y manifiesto declara `analytics.v_consumo_mensual`.

**Alternativas:** reconstruir la ingesta; repetir componentes al unirlos con hechos; guardar JSON personal en claro. Se descartan por riesgo de regresión, doble suma y exposición de PII, respectivamente.

**Calidad:** releer únicamente fuentes aceptadas y comprobadas por hash, reutilizando normalización S03. Duplicados por firma normalizada: cada repetición histórica es exacta; una firma nueva para la misma clave es conflictiva. Rechazos B4 independientes. Correcciones por incremento ganador de versión en orden de archivos/filas. Calendario completo por maestro y meses locales aceptados. Huérfanas cuenta facturas; redondeo HALF_UP solo al exportar la suma. Aplicar A01 sin recuperar versiones descartadas.

**Consecuencias:** CSV/DQ estables al repetir, métricas operativas de consumos/facturas por intento (escrituras incluyen actualizaciones). La relectura para DQ tiene costo de procesamiento y no incrementa filas de nueva ingesta. Sin dependencia nueva ni copia SQL de entradas crudas. Si desaparece o cambia una fuente aceptada, no se puede reconstruir fielmente su calidad: se falla preservando los datos confirmados.

**Publicación:** preparar los tres documentos y reemplazar cada archivo completo; error retorna fallo, nunca éxito aparente. No existe atomicidad conjunta entre los tres reemplazos ni entre archivos y PostgreSQL. Un fallo intermedio puede dejar resultados de ejecuciones diferentes; reejecutar regenera. Sin transacciones distribuidas ni mecanismo adicional fuera del alcance.
