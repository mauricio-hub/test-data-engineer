# S04 — Facturación, calidad y publicación

Estado: propuesto. Fase 4 no autorizada. Depende de S03.

## 1. Objetivo
Producir resultados mensuales y reportes de calidad confiables, con facturas relacionadas correctamente y sin exponer datos personales.

## 2. Qué vamos a construir
- Leer facturación JSON anidada; separar factura y componentes, relacionándolos por identificadores técnicos.
- Proteger los datos personales anidados y enviar facturas huérfanas a cuarentena.
- Publicar agregados desde datos confirmados. Escribir cada archivo completo antes de sustituir su versión anterior; no publicar como exitosa una transacción fallida.

## 3. Cómo sabemos que funciona
- **T04/T14:** las relaciones son válidas; una factura huérfana no entra al modelo y queda en cuarentena con motivo. Sus componentes no multiplican el consumo al sumar.
- **T32:** `out/consumo_mensual.csv` tiene exactamente la cabecera `frontera_id,mes,consumo_kwh,horas_con_dato`, mes local `YYYY-MM` y consumo con tres decimales. Hay una fila por frontera-mes con lectura válida; las horas cuentan lecturas horarias únicas válidas. El orden es estable.
- **T13:** los huecos siguen A05 e incluyen ausencias y lecturas ganadoras inválidas según A01. Nunca se rellena consumo.
- **T32:** `out/dq_report.json` contiene conteos enteros no negativos y estas claves obligatorias:
  - `filas_leidas`, `duplicados_exactos`, `duplicados_conflictivos`.
  - `registros_negativos`, `registros_nulos`, `registros_outlier`, `registros_mwh_convertidos`.
  - `correcciones_tardias_aplicadas`, `horas_sin_lectura_valida_total`.
  - `horas_sin_lectura_valida_por_frontera`: objeto con conteos por frontera.
  - `fronteras_huerfanas_facturacion`, `clientes_con_pii_en_texto_libre`.
- **T11/T16:** los conteos siguen A02/A03/A06 aprobados; duplicados cuentan filas sobrantes, no grupos; los clientes afectados se cuentan una sola vez.
- **T27:** `out/metrics.json` incluye filas leídas y cargadas, rechazadas por motivo, duración por etapa y fecha/hora de ejecución. Distingue escrituras efectivas del tamaño total del conjunto de datos.
- **T01/T26:** `logs/pipeline.log` tiene un JSON válido por línea, sin datos personales, incluso al provocar errores.
- **T05/T32:** se crean `out/` y `logs/` si faltan. Las salidas se regeneran desde entradas/base sin depender de archivos anteriores. CSV y reporte de calidad se mantienen iguales bajo A04.

## 4. Qué no haremos todavía
No añadir conciliación monetaria, dashboards ni reglas comerciales de rechazo no solicitadas.

## 5. Decisiones pendientes
Resolver A02–A06 y aplicar A01: contadores, igualdad entre ejecuciones, huecos, huérfanas y redondeo.

## 6. Referencias técnicas
- README §4: Partes A, B y E; §5: formatos exactos de salida.
- Pruebas: T01, T04, T05, T11, T13, T14, T16, T26, T27 y T32.

## 7. Archivos y responsabilidades

**Archivos que se crearán:** filas «Crear». **Archivos que se modificarán:** filas «Modificar»; se reutilizan los módulos de S02/S03, no un segundo pipeline.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/quality/reports.py` | Calcular huecos/conteos y publicar CSV/JSON exactos mediante escritura completa y sustitución segura. |
| Crear | `sql/004_billing.sql` | Definir facturas/componentes y vista mensual sin PII, con claves y permisos. |
| Crear | `tests/test_quality.py` | Verificar calendarios, contadores, precisión y contratos de archivos con resultados independientes. |
| Modificar | `src/batch/extract.py` | Añadir lectura del JSON de facturación, sin duplicar descubrimiento. |
| Modificar | `src/batch/transform.py` | Separar factura/componentes y proteger o evitar copias de datos personales redundantes. |
| Modificar | `src/batch/load.py` | Persistir facturación válida y cuarentena; consultar agregados sin multiplicarlos por componentes. |
| Modificar | `src/batch/pipeline.py` | Coordinar el recorrido batch completo y entregar resultados a reportes. |
| Modificar | `src/quality/validators.py` | Añadir validación de referencias de facturación y consistencia necesaria para reportar. |
| Modificar | `src/security/classification.py` | Incorporar contratos de columnas de facturas/vistas y comprobar su protección. |
| Modificar | `data_classification.yaml` | Clasificar las columnas introducidas por el SQL de S04. |
| Modificar | `src/observability.py` | Incorporar duración por etapa y métricas permitidas; mantener una sola construcción de logs. |
| Modificar | `tools/manage.py` | Registrar SQL y objetos del manifiesto y dirigir `run` al coordinador completo, sin implementar reglas de datos. |
| Modificar | `tests/test_batch_database.py` | Añadir integración de facturas, huérfanos y agregaciones, reutilizando `tests/db_helpers.py`. |
| Modificar | `specs/S04-quality.md` | Registrar semántica aprobada de reportes y aceptación. |
| Modificar | `specs/TRACEABILITY.md` | Registrar precisión y contratos comprobados. |
| Modificar | `DECISIONS.md` | Justificar modelado de facturación, calendario y publicación. |

**Responsabilidades y relación:** batch conserva extracción/carga; validadores deciden validez; reportes reciben resultados y publican archivos. Observabilidad define los campos seguros de logs/métricas. Reportes no abre conexiones ni importa coordinadores; la carga proporciona las consultas necesarias.

**Restricciones:** conservar `analytics.v_clientes` y crear, como propuesta, `analytics.v_consumo_mensual` para la salida mensual. El cambio de `vista_analytics` en el manifiesto se debe aprobar con ese SQL, no inventar un objeto para el verificador. El manifiesto se genera mediante `tools/manage.py`; no mantener nombres divergentes manualmente. No cambiar formatos del README, nombres de comandos Make, datos originales, puertos ni llaves.

**Pruebas:** `tests/test_quality.py` cubre T11/T13/T16/T27/T32; `tests/test_batch_database.py` cubre T04/T05/T14 y su publicación integrada. Reutilizar `tests/test_privacy.py` para T01/T26; verificar por separado ausencia de PII en salidas reales. `out/consumo_mensual.csv`, `out/dq_report.json`, `out/metrics.json` y `logs/pipeline.log` son generados, no módulos ni resultados preconstruidos.

**Decisiones pendientes adicionales:** esquema de facturación, interfaz de agregados y vista final; resolver A01–A06 relevantes. El nombre de vista propuesto no cambia ahora ningún objeto existente.
