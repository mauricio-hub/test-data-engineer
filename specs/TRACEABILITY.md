# Matriz de trazabilidad

## Estado consolidado al iniciar S06

El responsable confirmó S01–S05 validadas en Windows: `make run` funcional, streaming con 3.795 eventos/33 alertas y resultados idénticos, y `make test` con 43 pruebas aprobadas. Esta es evidencia comunicada por el operador, no una nueva ejecución del agente en S06. Las incidencias y omisiones de registros anteriores son históricas y no deben leerse como el estado final de S05.

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

## Evidencia de S03 — plan reducido autorizado

- Línea base: 34 pruebas aprobadas, con `S01_PSQL=C:/Program Files/PostgreSQL/17/bin/psql.exe` y dependencias existentes. Integración posterior: 37 pruebas aprobadas (34 conservadas y tres escenarios nuevos en `tests/test_batch.py`).
- T09–T12: formatos existentes, coma decimal, conversión MWh, UTC cruzando mes local, límites B4 y desempate por versión/nombre/fila. La carga de originales usa los tres formatos, sin meses codificados.
- T05–T08: originales cargados únicamente en una base temporal propia, reejecución idéntica de negocio/cuarentena, mes sintético descubierto y archivo truncado completo rechazado sin alterar hechos anteriores. Hashes de todos los originales iguales antes/después.
- A01/T06: corrección inválida conserva versión y elimina el hecho; original y copia de menor versión no lo restauran. Una versión posterior válida sí recupera la lectura. Cambiar contenido bajo igual nombre se rechaza sin sustituir lo aplicado.
- T15/T17–T19/T26: clasificación nueva contra catálogo real; evidencia cifrada y recuperable con contexto; analista/auditor sin acceso a nuevas tablas base; ingesta sin TRUNCATE ni DELETE en auditoría. Error SQL provocado revierte archivo completo, conserva negocio y registra resultado `failed`; mensaje y logs no exponen la PII sintética del error.
- SQL 003 aplicado dos veces en base temporal para comprobar repetibilidad. Pruebas conectadas al PostgreSQL disponible en `127.0.0.1:55432`; no se cargaron originales en la base operativa ni se generó una llave de aplicación. Llave de pruebas solo en memoria y datos temporales eliminados al cerrar la suite.
- Pendiente: recorrido Docker/Make (acceso al motor denegado), ejecución con la llave externa del operador y contrato completo de `make run`. S04 debe añadir facturación, vista analítica definitiva, reportes de calidad, agregados y métricas contractuales. A02/A03/A05 y redondeo/huérfanas de A06 se concretarán al aprobar S04.

## Evidencia de S04 — alcance reducido aprobado

- Línea base: 37 pruebas aprobadas. Suite final: **40 pruebas aprobadas**, ninguna fallida; 37 conservadas sin cambios y tres escenarios en `tests/test_quality.py`. Comando: `python -B -m unittest discover -s tests -q`, con `S01_PSQL` apuntando al psql local existente.
- T04/T14/T17/T18: facturas y componentes relacionados; dos facturas sintéticas para la misma frontera desconocida cuentan como dos huérfanas. Evidencia y datos privados cifrados antes de SQL; reintento conserva filas/cifrados. Columnas nuevas cubiertas por clasificación; degradar payload a Interno falla. Roles probados con conexiones reales, incluida vista analítica de solo lectura.
- T11/T13/T27/T32: caso pequeño independiente con año bisiesto, cruce UTC de mes, MWh, cero válido, nulo, negativo, outlier, duplicados y A01; contrato CSV exacto, redondeo HALF_UP y las 12 claves/tipos del reporte. Publicación fallida antes de sustituir archivos conserva salidas y retorna fallo sin PII.
- Integración de originales en una base temporal propia: primera ejecución **25,211 s**, 115.512 registros de consumo/facturación procesados, 115.005 escrituras válidas (incluye actualizaciones), 195 rechazos B4 y 12 facturas huérfanas; cero archivos rechazados. Segunda **2,144 s**, cero nueva ingesta/escrituras/rechazos. CSV/DQ idénticos; regeneración en otro directorio vacío idéntica.
- Resultado acumulado: 160 filas mensuales y 114.545 horas válidas; 180 duplicados exactos, 420 conflictivos, 400 conversiones MWh, 300 correcciones, 655 huecos, 12 facturas huérfanas y 25 clientes con PII en texto libre. Los tres archivos generados en el `out/` temporal fueron `consumo_mensual.csv`, `dq_report.json` y `metrics.json`; fixtures y bases se eliminaron al finalizar.
- T19/T26: error de publicación real provocado, retorno 1, auditoría `failed` y log JSON sin el dato personal sintético de la excepción. El punto de entrada de `tools/manage.py run` delega al mismo módulo probado, propaga retorno 0/1 y conserva límite de 900 s.
- Conservación: hashes de originales iguales antes/después. Sin cambios de credenciales, puertos, volúmenes, Makefile, Compose, pruebas anteriores ni algoritmos S03. Sin llave operativa generada ni carga de facturas en la base del usuario.
- **No certificado:** ejecución literal de `make run`/Docker: GNU Make no está disponible y no hay `BIA_PII_KEY_FILE` configurada en este proceso. Las ejecuciones anteriores corresponden a `pipeline.main` con conexión/llave de fixture en PostgreSQL real, no a la base operativa. No se generaron resultados S04 en el `out/` del proyecto.
- Pendiente local: `make up` para aplicar SQL 004 y actualizar manifiesto; configurar explícitamente la llave externa existente; `make run` dos veces y `make test`. Pendientes de fases siguientes: S05, validación final, video y empaquetado. Límites de publicación y fuentes modificadas documentados en S04/ADR-008.

## Evidencia parcial de S05 — alcance reducido aprobado

- Usuario validó S04 localmente: `make run` y las 40 pruebas satisfactorias. Línea base S05 en este entorno: las mismas 40 pruebas aprobadas.
- T22–T24/T32: dos escenarios nuevos aprobados. Verifican banda estricta (igualdad no alerta), máximo temporal que no retrocede, tercero ausente, recuperación, ausencias iniciales/finales, dos intervalos sin alerta y presencia tardía que divide la racha. Salida con tres campos, offset Colombia y sin duplicados.
- T25/T26/T31: pruebas controladas de rango que excluye históricos/futuros, rango incompleto, timeout, productor fallido, cierre de clientes y conexión, error de publicación y preservación de salida previa. Logs/mensajes sin contenido sintético privado; auditoría utiliza operación stream y el mismo control SQL S01.
- Primera suite posterior: 43 pruebas, 41 aprobadas, 1 fallida y 1 omitida. Fallo: la lista cerrada de dependencias S01 no contemplaba kafka-python. El usuario autorizó posteriormente cambiar solo esa lista en `tests/test_setup.py`; se añadió el paquete sin alterar ninguna otra validación. **Suite final: 43 pruebas, 42 aprobadas, cero fallidas y una integración omitida**, en 66,725 s.
- Integración real omitida explícitamente por falta de kafka-python. TCP a Redpanda 9092 accesible; instalación de la versión 2.3.2 no disponible mediante pip en este entorno. Existencia de esa versión comprobada en PyPI oficial. No afirmar consumo Kafka, ejecución real del productor ni make stream aprobados.
- Referencia del algoritmo, **leyendo el archivo original directamente y sin Kafka**: 3.795 eventos; 22 alertas de banda, 6 de ausencia y 5 retroactivas (33 total). Estos conteos no certifican la reproducción Kafka y no se publicaron como un resultado de make stream.
- Prueba preparada en `tests/test_streaming_integration.py`: tópico con UUID propio, productor original dos veces, comparación de alertas, conteo dinámico, aislamiento de históricos y limpieza exclusivamente de su tópico. Con dependencia instalada, un fallo de Redpanda causa fallo real, no omisión.
- Cambios limitados al plan S05: sin modificar productor, originales, Makefile, Compose, roles, tablas, llaves ni credenciales. Escritor S04 extraído dentro del mismo archivo conservando su algoritmo/interfaz; batch conserva valor por defecto de auditoría.
- Ejecución real del punto de entrada `python tools/manage.py stream`: retorno 1 con motivo `dependency_missing`, cero eventos consumidos y sin crear alertas ficticias; evento seguro en 0,063 s. Consulta de solo lectura como auditor confirmó `operation=stream`, `result=failed`, `rows_read=0`, `rows_loaded=0`.
- Pendiente: instalar la dependencia, ejecutar integración real y make stream dos veces. Comandos locales: `make setup`, `make up`, `make stream`, `make stream`, `make test`. Streaming no requiere llave PII: solo lee identificadores/límites y audita con la cuenta existente.

## Evidencia de S06 — documentación e IaC sin despliegue

- T21: `THREAT_MODEL.md` contiene flujo/fronteras de confianza y diez amenazas concretas que cubren STRIDE, probabilidad/impacto, referencias al código/tests, estado y riesgo residual. Mapeo de referencia Anexo A 2022 contrastado con extractos normativos indexados; no constituye certificación. La copia íntegra de la norma no se pudo descargar.
- T30: cuatro documentos nuevos (SECURITY, THREAT_MODEL, AI_USAGE, RUNBOOK), diez ADRs actualizados y README ampliado. AI_USAGE incluye tres extractos textuales reales y el error de la firma end_offsets en consumer.py:152/158, con la regresión autospec. No se atribuyen a la IA las ejecuciones Windows comunicadas por el responsable.
- T28 parcial: `infra/main.tf` describe un bucket privado/versionado con SSE-KMS y TLS, una llave con administración separada y tres roles con confianza explícita/distinta. S3 Get/Put/List y KMS Decrypt/GenerateDataKey están separados por prefijos y contexto de objeto, sin permisos de borrado o administración para roles operativos. Sin data sources AWS, usuarios/llaves IAM, cómputo ni integración S3 ficticia.
- **T28 pendiente:** Terraform no está instalado, tampoco un parser HCL disponible. No se ejecutaron ni se declaran aprobados fmt/init/validate. Revisión manual de referencias/políticas no sustituye validación de proveedor. No se generó `.terraform.lock.hcl`; solo se versionará si init real lo genera. No hubo plan/apply ni llamadas AWS.
- T34 parcial: enunciado original de README conservado íntegramente como prefijo de texto; instrucciones agregadas al final. Diez amenazas/diez ADRs y enlaces locales comprobados. `.gitignore` verificado con rutas sintéticas: data/, .terraform/, estados/backups, tfvars, planes y llaves ignorados; lockfile no ignorado.
- Conservación: 72 archivos protegidos por hash, incluidos originales, entrega.yaml y tools/manage.py, sin cambios. No se modificó código funcional ni se ejecutaron objetivos Make, pruebas funcionales o servicios en esta fase.
- Riesgos residuales: Kafka local sin autenticación/TLS; ACL Windows externa, llave Fernet sin rotación automática; tamaño/memoria no limitados globalmente; superusuario fuera de garantía de inmutabilidad; publicación no transaccional conjunta; S3 versionado sin WORM ni auditoría cloud. Descripción completa en documentos/ADR-010.
- Pendientes S07: validación del manifiesto y su generador (no_implementado antiguo), ejecución final completa, revisión de secretos/historial, video y empaquetado. S06 no altera esos archivos ni declara entrega final completa.
