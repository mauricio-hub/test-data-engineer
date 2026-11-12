# Decisiones iniciales de arquitectura

Fecha inicial: 2026-11-10. Arquitectura general, S01 y S02 autorizados. Se implementaron preparación, auditoría y privacidad de clientes; el pipeline completo sigue pendiente de S03/S04. Ver `specs/AMBIGUITIES.md`.

## ADR-001 — ETL local con Python y agregación SQL
**Estado:** propuesta dentro de arquitectura general aprobada.
**Contexto:** entradas heterogéneas y PII que no debe quedar en claro en base.
**Opciones:** ETL en Python; ELT con carga cruda en PostgreSQL; motor distribuido.
**Propuesta:** parsear, normalizar y proteger antes de cargar; agregar con SQL. Archivos originales siguen como origen inmutable; no usar MinIO local sin necesidad.
**Razón y consecuencias:** reduce copias de PII y servicios; se renuncia a una capa raw SQL y a procesamiento distribuido innecesario para el volumen.

## ADR-002 — Modelo relacional pequeño con hechos horarios
**Estado:** clientes, cuarentena y vista de identificadores implementados en S02. Fronteras, límites, consumos y facturación siguen pendientes de S03/S04.
**Contexto:** consumo horario, maestros y facturas anidadas.
**Opciones:** JSON crudo; tabla plana única; dimensiones y hechos relacionados.
**Propuesta:** clientes/fronteras/límites, consumo único por frontera-hora, factura y componentes separados; vista analítica sin PII.
**Razón y consecuencias:** integridad y agregación claras, sin duplicación por componentes. Más tablas que una única tabla plana; no introducir historial dimensional sin requisito.

## ADR-003 — Precedencia persistida y transacción por archivo
**Estado:** propuesta; bloqueada por A01–A04.
**Contexto:** correcciones, empates y archivos corruptos sin regresión.
**Opciones:** recargar todo; sobrescribir por llegada; comparar precedencia persistida.
**Propuesta:** versión + nombre lexicográfico + posición lógica; hash de contenido y transacción por archivo. No actualizar filas sin cambio.
**Razón y consecuencias:** aplica correcciones incrementales y aísla corrupción. Requiere metadatos y semántica explícita de métricas; no resuelve automáticamente reemplazos de archivo bajo igual nombre.

## ADR-004 — Cifrado autenticado en aplicación
**Estado:** implementada en S02; validación con dependencias fijadas pendiente de instalación.
**Contexto:** el evaluador consulta tablas como superusuario.
**Opciones:** cifrado de disco; pgcrypto con llaves accesibles a base; cifrado en aplicación.
**Propuesta:** cifrar Restringido-PII antes de SQL; llave externa a base/paquete, clasificación activa, joins por identificadores técnicos.
**Razón y consecuencias:** dump no expone texto claro. Compromiso del proceso con llave sigue siendo riesgo; requiere custodia de llave y no permite buscar directamente por ciphertext aleatorio.

**Concreción S02:** Fernet de `cryptography` (cifrado autenticado), prefijo `fernet:v1:` y contexto de cliente/columna dentro del mensaje autenticado para impedir intercambios de ciphertext. Todos los textos del maestro se cifran, incluidas observaciones previamente enmascaradas. Los datos originales permanecen intactos. La llave se lee solo desde `BIA_PII_KEY_FILE`, fuera del repositorio; falta/llave incorrecta implica fallo. No se implementa rotación automática; cambiar la llave exige una migración posterior explícita. Enmascaramiento heurístico conservador: no se promete detectar toda PII imaginable, por eso el texto libre no se publica.

## ADR-005 — Propiedad separada y roles operativos mínimos
**Estado:** auditoría y permisos de clientes implementados en S01/S02. Permisos de consumos pendientes de S03. Validación con Compose pendiente.
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
