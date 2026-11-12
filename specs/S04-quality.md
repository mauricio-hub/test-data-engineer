# S04 — Facturación, calidad y publicación

Estado: alcance reducido e interpretaciones aprobados por el usuario. Implementado; validación del contrato Make en la máquina del operador pendiente.

## 1. Objetivo
Completar el batch: facturación segura, calidad verificable y salidas exactas, reutilizando S03.

## 2. Qué vamos a construir
- Facturas y componentes relacionados; huérfanas en cuarentena cifrada, sin cargar sus componentes. Protección de emisor, cliente, pago y concepto antes de SQL.
- Vista `analytics.v_consumo_mensual` sobre hechos válidos, sin unir componentes ni exponer PII. Conservar `analytics.v_clientes`.
- Reporte estable desde entradas aceptadas y métricas del trabajo de cada intento.
- Conectar `make run` mediante `tools/manage.py`, sin cambiar Makefile.

## 3. Cómo sabemos que funciona
- **T04/T14/T17/T18:** facturas con clave y frontera referenciada; componentes con clave factura/posición. Repetir no duplica ni cambia cifrados. Huérfanas consultables solo como evidencia cifrada; roles sin privilegios adicionales sobre tablas base.
- **T32:** CSV con cabecera exacta `frontera_id,mes,consumo_kwh,horas_con_dato`; mes Colombia, orden frontera/mes y una fila por combinación con lectura válida. Sumar sin redondear; exportar tres decimales con ROUND_HALF_UP.
- **T11/T13/T16/T32:** JSON con las 12 claves de README §5, enteros no negativos y mapa de huecos por frontera. Firma normalizada: frontera, hora, kWh, versión y calidad; cada fila sobrante cuenta una vez, exacta si la firma ya apareció y conflictiva si es nueva. B4 se cuenta independientemente.
- **T05:** calidad acumulada y CSV idénticos al reejecutar. Correcciones: incrementos de versión ganadores al recorrer archivos y filas; no inferirlas del nombre.
- **T13:** calendario completo de todas las fronteras y meses locales de entradas aceptadas, sin filtros por estado/fecha. A01 conserva ganadores inválidos como huecos. Huérfanas: contar facturas, aunque compartan frontera.
- **T27:** métricas con filas de consumo/facturación efectivamente procesadas, escrituras, nuevos rechazos por motivo, duraciones y timestamp. Cargadas incluye actualizaciones. La relectura para calidad no es nueva ingesta.
- **T26/T32:** crear directorios, preparar archivos completos y reemplazarlos individualmente. Error de publicación/log termina con código distinto de cero, sin mensajes con contenido personal.
- Tres escenarios en `tests/test_quality.py`; conservar y ejecutar las 37 pruebas anteriores.

## 4. Qué no haremos todavía
Sin streaming/alertas, conciliación monetaria, nuevas dependencias ni refactorización S01–S03. Sin corrección automática de facturas o archivos existentes: contenido cambiado bajo igual nombre se rechaza. Un identificador de factura ya cargado en otro archivo se rechaza como estructura conflictiva.

Limitaciones: los tres reemplazos de salida no son una transacción conjunta; un fallo entre reemplazos puede dejar archivos de ejecuciones distintas, siempre completos, y retorna error. Reejecutar los regenera. Si falta/cambia una entrada aceptada, calidad falla sin inventar su contenido. Los archivos de negocio ya confirmados permanecen ante un fallo posterior. La auditoría de fallo requiere conexión disponible.

## 5. Decisiones pendientes
A01–A06 aprobadas internamente; no equivalen a confirmación de Bia. Validar `make up` y `make run` dos veces en la máquina del operador con su llave externa existente. Este entorno no tiene GNU Make ni llave PII configurada; pruebas usan una base propia y llave efímera solo en memoria.

## 6. Referencias técnicas
README §4 Partes A, B1–B7, C1–C5 y E; §5 formatos exactos. T01/T04/T05/T11/T13/T14/T16–T19/T26/T27/T32. `alertas.json` pertenece a S05.

## 7. Archivos y responsabilidades

**Archivos que se crearán:** filas Crear. **Archivos que se modificarán:** filas Modificar.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/quality/__init__.py` | Identificar el paquete sin efectos al importar. |
| Crear | `src/quality/reports.py` | Calidad estable, calendario y publicación CSV/JSON. |
| Crear | `sql/004_billing.sql` | Registro de archivos, facturas, componentes, cuarentena, vista y permisos. |
| Crear | `tests/test_quality.py` | Tres escenarios; reutilizar fixtures S03 sin heredar sus tests. |
| Modificar | `src/batch/extract.py` | Leer JSON con precisión decimal. |
| Modificar | `src/batch/transform.py` | Separar facturación y contenido privado. |
| Modificar | `src/batch/load.py` | Persistir facturas/cuarentena y consultar contexto de reportes. |
| Modificar | `src/batch/pipeline.py` | Añadir recorrido completo conservando `run` de S03. |
| Modificar | `src/security/classification.py` | Validar columnas S04 con ámbito explícito; conservar ámbito S02/S03 por defecto. |
| Modificar | `data_classification.yaml` | Clasificar todas las columnas nuevas. |
| Modificar | `src/observability.py` | Métricas seguras por intento. |
| Modificar | `tools/manage.py` | Aplicar SQL 004, declarar vista y dirigir run al módulo batch. |
| Modificar | `specs/S04-quality.md` | Alcance y limitaciones. |
| Modificar | `specs/AMBIGUITIES.md` | Registrar aprobación interna A01–A06. |
| Modificar | `specs/TRACEABILITY.md` | Evidencia de validación. |
| Modificar | `DECISIONS.md` | Decisiones S04 y consecuencias. |

**Relación:** coordinador llama ingesta y reportes; reportes reutiliza normalización y recibe consultas ya resueltas, sin abrir conexiones ni importar coordinadores. Sin validadores, auxiliares o módulos adicionales.

**Restricciones:** no cambiar originales, llaves, credenciales, puertos, volúmenes, Makefile, Compose, algoritmos S03 ni pruebas anteriores.
