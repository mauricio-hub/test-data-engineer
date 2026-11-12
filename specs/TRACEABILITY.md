# Matriz ejecutiva de trazabilidad

Fuente: README §§4–9, Makefile, specs S01–S07 y plantillas. T01–T34 son referencias de cobertura, no una prueba automática por fila.
Base S01–S05 confirmada en Windows: 43 pruebas aprobadas. Suite S07 ejecutada: 47 aprobadas en 93,748 s, sin fallos ni omisiones; incluye Kafka real.
S06: validate satisfactorio con Terraform 1.17.1, confirmado por el responsable; sin despliegue AWS. Las pruebas nuevas de S07 no sustituyen el cierre final.
Estado: Validado = evidencia local; Parcial = falta una comprobación; Implementado = pendiente de aceptación final; Pendiente = no ejecutado.

| Área/requisito | Implementación | Verificación | Estado |
|---|---|---|---|
| Infraestructura — entorno y servicios | S01; Makefile, Compose, `tools/manage.py` | T31: setup/up y conexiones; puerto PostgreSQL 55432, Kafka IPv4 9092 | Validado; recorrido final pendiente |
| Seguridad — **X1 eliminatorio: PII** | S02/S04; cifrado, vistas y eventos seguros | T01, T17, T18, T26; privacidad y permisos reales | Validado local; paquete final pendiente |
| Seguridad — **X2 eliminatorio: secreto heredado** | S01; credenciales nuevas y exclusión de secretos | T02; setup, revisión de fuentes/objetos Git y paquete | Parcial: revisión final y referencia histórica |
| Seguridad — **X3 eliminatorio: SQL hostil** | S02/S03; parser completo y SQL parametrizado | T03; `tests/test_privacy_database.py`, consumo preservado | Validado |
| Seguridad — C1 clasificación activa | S02/S04; `Classification`, política YAML | T15; columnas faltantes y degradación rechazadas | Validado |
| Seguridad — C2 PII en texto libre | S02; `mask_pii`, conteo por cliente | T16; `tests/test_privacy.py` y reporte DQ | Validado; detección heurística |
| Seguridad — C3 cifrado previo a SQL | S02/S04; `Cipher`, cuarentenas protegidas | T17; lectura como administrador y contexto autenticado | Validado |
| Seguridad — C4 mínimo privilegio | S01–S04; SQL 001–004, tres roles | T18; `tests/test_access.py` y privacidad/facturación | Validado |
| Seguridad — C5 registro de auditoría | S01; `audit.record_run`, actor de sesión | T19; UPDATE/DELETE/TRUNCATE denegados a roles operativos | Validado; superusuario fuera de garantía |
| Seguridad — C7 dependencias | `requirements.txt`, SECURITY.md | T20; inventario/pins y lista esperada en setup | Parcial: sin auditoría CVE certificada |
| Seguridad — C8 amenazas | S06; THREAT_MODEL.md, diez amenazas STRIDE | T21; código/tests, estados y mapeo Anexo A 2022 | Implementado; revisión editorial final |
| Batch — modelo y relaciones | S03/S04; SQL 002–004 y ADR-002 | T04; claves, facturas/componentes y vista mensual | Validado |
| Batch — idempotencia | S03/S04; hash, precedencia y escrituras condicionales | T05; negocio/cuarentena y CSV/DQ estables | Validado; cierre final pendiente |
| Batch — correcciones tardías | S03; estado persistido por frontera/hora | T06; original → corrección → original; A01 | Validado |
| Batch — cuarentena consultable | S02–S04; tablas de rechazo cifradas | T07; motivos, evidencia y reintentos sin duplicados | Validado |
| Batch — descubrimiento/corrupción | S03; formatos por cabecera y transacción por archivo | T08; mes sintético nuevo y archivo truncado | Validado |
| Calidad — B1 hora Colombia | S03/S04; normalización UTC−5 | T09; UTC cruzando mes local | Validado |
| Calidad — B2 unidades | S03; Decimal y conversión MWh por fila | T10; coma decimal, kWh/MWh | Validado |
| Calidad — B3 duplicados | S03/S04; versión, nombre y fila lógica | T11; desempates y conteo de filas sobrantes | Validado; interpretación interna aprobada |
| Calidad — B4 inválidos | S03; vacío, negativo, >1.000.000; A01 | T12; cero/límite válidos y ganador inválido sin hecho | Validado |
| Calidad — B5 huecos | S04; calendario completo, sin imputación | T13; ausencias y lecturas descartadas | Validado; A05 aprobada internamente |
| Calidad — B6 facturas huérfanas | S04; FK y cuarentena cifrada | T14; rechazo sin factura/componentes cargados | Validado |
| Streaming — banda estricta | S05; `AlertEngine` | T22; mayor que máximo, igualdad no alerta | Validado |
| Streaming — retroactividad | S05; máximo temporal por frontera | T23; atrasos no reducen el máximo | Validado |
| Streaming — ausencia/recuperación | S05; 96 intervalos, A07 al cierre | T24; tercero ausente, extremos y recuperación | Validado; interpretación interna aprobada |
| Streaming — Kafka real y replay | S05; productor original y rango de offsets | T25; integración real, 3.795 eventos y 33 alertas por ejecución | Validado en Windows; salidas idénticas |
| Observabilidad — logs JSON sin PII | S02–S05; códigos, conteos y etapas | T26; errores de driver/productor/publicación sin payload | Validado local; revisión final pendiente |
| Observabilidad — métricas y operación | S04/S06; metrics.json y RUNBOOK.md | T27; conteos, duración, timestamp y recuperación | Implementado/verificado; revisión final |
| Terraform — S3/KMS/IAM | S06; infra/main.tf y lockfile versionado | T28; validate satisfactorio en Windows; fmt final por registrar | Validado sintácticamente; no desplegado |
| Entrega — ingeniería Python/SQL | S01–S07; módulos y pruebas existentes/nuevas | T29; 47 pruebas aprobadas, incluidas regresiones de manifiesto/empaquetado | Validado local; cierre contractual pendiente |
| Entrega — ADRs, seguridad y uso de IA | S06; diez ADRs y documentos obligatorios | T30; prompts/errores reales y referencias verificables | Implementado; cierre editorial pendiente |
| Entrega — contrato completo | S07; mismos comandos Make | T31; setup/up/run×2/stream/test/verificar/down y tiempos | Pendiente del recorrido final; down no autorizado ahora |
| Entrega — formatos exactos | S04/S05; CSV mensual, DQ, métricas, alertas | T32; claves/tipos, precisión, offset, regeneración | Validado local; verificar paquete definitivo |
| Entrega — manifiesto coherente | S07; prepare conserva datos/objetos/secretos y corrige declaración antigua | T33; regresión setup y make verificar con servicios activos | Parcial: faltan datos del candidato y verificar final |
| Entrega — ZIP e historial | S07; `tools/package_delivery.py`, biblioteca estándar | T34; extracción, CRC, Git fsck y tres pruebas de paquete aprobadas | ZIP temporales verificados; definitivo no autorizado |

## Riesgos y pendientes reales

- Completar candidato, horas reales y nombre del ZIP; aprobar recorrido final, video y paquete. No se ejecuta make down, commit o push automáticamente.
- No_implementado describe capacidades realmente faltantes, no tareas de cierre; setup elimina solo declaraciones antiguas conocidas y conserva faltantes concretos.
- El ZIP definitivo y su historial requieren revisión final: solo entrega.yaml admite credenciales efímeras; no llave Fernet, datos, entornos, volúmenes ni estados Terraform.
- Kafka local sin autenticación/TLS y un solo productor por replay; custodia ACL/llave externa; sin rotación automática ni transacción conjunta de archivos/SQL/Kafka.
- Escaneos de secretos y validación Terraform tienen alcance limitado; no prueban ausencia universal de secretos, vulnerabilidades o autorización AWS. Detalles en SECURITY.md y THREAT_MODEL.md.
