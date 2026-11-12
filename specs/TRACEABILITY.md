# Matriz de trazabilidad

Fuente: README §§4–9; Makefile; entrega.yaml; plantillas. La tabla describe cobertura prevista; la ejecución parcial de S01 figura al final. Los puntos pertenecen al bloque, no se atribuyen a cada fila.

| Requisito / criterio | Evaluación | Spec | Prueba y evidencia prevista |
|---|---|---|---|
| X1: PII ausente en logs/out y para analista | Eliminatorio | S02, S04, S07 | T01: buscar valores sensibles y patrones; conectar como analista |
| X2: secreto heredado retirado de uso y entrega | Eliminatorio | S01, S07 | T02: inspección de configuración efectiva y paquete; ver A10 |
| X3/B7: entrada hostil nunca ejecutada; sin pérdida silenciosa | Eliminatorio; B/G | S02, S03 | T03: 40 clientes conservados y tabla de consumos intacta; CSV multilínea sintético |
| A: modelo SQL analítico justificado | A: 24; revisión humana | S03, S04 | T04: claves, relaciones, tipos y revisión ADR-002 |
| A: idempotencia | A: 24 | S03, S07 | T05: dos corridas; mismo estado de negocio y salidas estables |
| A: correcciones incrementales | A: 24 | S03 | T06: original → corrección → original, sin regresión ni recarga completa |
| A: cuarentena consultable y motivada | A: 24 | S02, S03, S04 | T07: rechazo localizable, protegido y sin duplicación por reintento |
| A: descubrimiento, mes nuevo y corrupción | A: 24 | S03 | T08: mes sintético y truncado; estado previo preservado |
| B1: hora y mes Colombia | B: 16 | S03, S04 | T09: UTC, offset y cruce de mes |
| B2: kWh y conversión por fila | B: 16 | S03 | T10: kWh/MWh y decimal con coma |
| B3: versión y desempate lexicográfico/fila | B: 16 | S03 | T11: versiones, empate entre archivos y orden incremental |
| B4: nulo, negativo y >1.000.000 | B: 16 | S03, S04 | T12: vacío, negativo, cero, límite y superior; A01 |
| B5: huecos sin imputar | B: 16 | S04 | T13: ausencia física y rechazo; calendario aprobado en A05 |
| B6: factura huérfana | B: 16 | S04 | T14: rechazo sin inserción en modelo |
| C1: clasificación por columna consumida | C: 31 | S02 | T15: cobertura del esquema y rechazo de clasificación faltante |
| C2: PII en observaciones y clientes afectados | C: 31 | S02, S04 | T16: correo/celular/cédula sintéticos y conteo por cliente |
| C3: cifrado visible como superusuario | C: 31 | S02 | T17: inspeccionar tablas, staging y cuarentena; descifrado controlado en test |
| C4: ingesta, analista, auditor | C: 31 | S01, S02 | T18: conexiones y permisos positivos/negativos, sin propiedad ni escalamiento |
| C5: auditoría append-only por corrida | C: 31 | S01, S03 | T19: quién/qué/cuándo/conteos/resultado; UPDATE/DELETE/TRUNCATE denegados |
| C6: secretos fuera del código | C: 31 | S01, S07 | T02: fuentes de secretos y credenciales locales coherentes |
| C7: revisión de dependencias | C: 31 | S01 | T20: inventario, necesidad y auditoría documentada |
| C8: ≥8 amenazas STRIDE + Anexo A 2022 | C: 31; revisión humana | S06 | T21: amenazas propias, controles y estado verificados |
| D: tres alertas, timestamps, sin duplicados | D: 9 | S05 | T22–T25: banda, retroactividad, caída y Kafka real |
| E: logs JSON sin PII | E: 8; X1 | S02, S04 | T01/T26: parsear cada línea y provocar errores sin fuga |
| E: métricas mínimas y runbook | E: 8 | S04, S06 | T27: esquema/conteos/duraciones; revisión de recuperación |
| F: S3 cifrado/versionado, KMS, IAM | F: 5 | S06 | T28: terraform validate y revisión de políticas; sin despliegue |
| G: Python/SQL, tests, legibilidad | G: 4 | S01–S07 | T29: suite y revisión de cambios; sin herramientas superfluas |
| H: ≥5 ADRs, AI_USAGE y honestidad | H: 3; plantillas | S06 | T30: decisiones con alternativas y evidencia real de uso de IA |
| Contrato: setup/up/run×2/stream/test/down | §5; puntos asociados | S01, S07 | T31: ejecución limpia; run ≤900 s, stream ≤300 s |
| Salidas: CSV mensual, DQ, alertas y métricas | §5 | S04, S05 | T32: nombres, claves, tipos, precisión, offset y regeneración |
| Manifiesto: candidato, conexiones y objetos con esquema | §5; entrega.yaml | S01, S07 | T33: make verificar y conexiones por rol/superusuario |
| ZIP, README, historial y exclusiones | §§6–8 | S06, S07 | T34: estructura/nombre, <10 MB como objetivo, sin data/venv/volúmenes; historial revisado |

La documentación no permite asignar con precisión los 76 puntos automáticos a cada subcriterio; no se inventa ese desglose.

## Evidencia parcial de S01

- T18/T19: aprobados sobre PostgreSQL 17.8 aislado, con conexiones reales y objetos sintéticos de negocio. No certifica modelo definitivo ni PostgreSQL 16 en Docker.
- T33: credenciales y conexión de cuatro usuarios verificadas; auditoría existente. Manifiesto completo y `make verificar` pendientes de datos del candidato y objetos S02–S04.
- T02: credenciales generadas/reutilizadas y configuración heredada retirada. El paquete final y su eventual historial se revisarán en S07.
- T20: inventario y versiones revisados; instalación y auditoría automática pendientes por acceso a PyPI bloqueado.
- T31: preparación repetible probada y configuración Compose válida; contrato Make/Compose no certificado por falta de GNU Make y motor Docker accesible.
- Detalle de comandos, límites y evidencias: [docs/S01.md](../docs/S01.md). Los demás criterios siguen pendientes.

## Evidencia parcial de S02

- T03/T15–T18: pruebas con CSV multilínea/textos largos, los 40 clientes, cobertura de clasificación, cifrado autenticado/contextual, rechazo de llave incorrecta, cuarentena cifrada y permisos reales. La carga original se verificó solo en una base temporal propia.
- T01/T26: stdout y logs JSON sin PII sintética, incluso ante una excepción real de PostgreSQL y reversión de carga parcial.
- C1: `data_classification.yaml` cubre el modelo actual y se valida contra columnas reales antes de escribir. No cubre modelos futuros todavía no implementados.
- S01: healthcheck cambiado a API administrativa sin `--brokers` ni espera; solo se inicializan contraseñas de roles que aún no tienen una. Datos originales y credenciales locales conservados, puerto 55432.
- No se declara contrato completo aprobado: Docker inaccesible; dependencia criptográfica fijada pendiente de instalación. Versiones de pruebas, llave y comandos PowerShell en [docs/S02.md](../docs/S02.md).

### Refactorización autorizada de S02

- Antes de modificar código: 31 pruebas aprobadas con `S01_PSQL` local y dependencias fijadas (Python 3.12.3, PyYAML 6.0.3, psycopg2 2.9.13 y cryptography 50.0.2). Después: las mismas 31 más tres pruebas de fachadas/CLI aprobadas, sin eliminar casos.
- La ejecución sin `S01_PSQL` falla antes y después al preparar la suite S01 porque Docker no es accesible; no se declara aprobado el recorrido Docker/Make.
- T01/T03/T15–T18/T26 mantienen sus resultados. Compatibilidad adicional: mismos parámetros/defaults públicos, intercambio de tokens entre versiones y mismos eventos con reloj fijo.
- Implementaciones únicas en `src/security/`, `src/client_service.py` y `src/observability.py`; `src/privacy.py` y `src/clients.py` delegan. No se crearon batch/calidad ni se modificó SQL, política, credenciales, puertos o datos originales.
