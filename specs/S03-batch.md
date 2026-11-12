# S03 — Ingesta y correcciones de consumos

Estado: plan reducido implementado y probado con PostgreSQL real. Suite completa: 37 pruebas aprobadas. Recorrido Docker/Make pendiente por permisos del entorno. Depende de S02.

## 1. Objetivo
Cargar consumos y correcciones sin duplicar datos, recuperar versiones reemplazadas ni dañar meses ya cargados.

## 2. Qué vamos a construir
- Descubrir los archivos de `data/consumos/` por nombre, sin meses fijos.
- Reconocer las tres cabeceras existentes, coma/punto y coma y UTF-8/Windows-1252. Leer registros CSV completos antes de escribir.
- Normalizar fechas a Colombia (UTC−5 fijo), convertir MWh por fila y conservar precisión decimal sin redondear para facturación.
- Guardar maestros, archivos, precedencia, hechos válidos y evidencia cifrada. Reutilizar clientes y seguridad S02 sin trasladar sus funciones.
- Confirmar cada archivo completo en una transacción. Conservar los archivos anteriores si otro archivo falla.

## 3. Cómo sabemos que funciona
- **T09/T10:** UTC puede cambiar el mes local; coma decimal y MWh producen kWh correctos.
- **T11:** gana `(version_lectura, nombre de archivo, posición lógica)`. El orden de llegada no cambia el ganador; SQL usa comparación de nombres con intercalación `C`.
- **T12/A01 aprobada:** seleccionar por precedencia antes de B4. Vacío, negativo y mayor de 1.000.000 se rechazan. Cero y exactamente 1.000.000 son válidos. Un ganador inválido conserva sus metadatos, elimina solo su hecho anterior y deja una hora sin lectura válida. Una versión inferior no la restaura.
- **T05/T06:** reintentar conserva negocio y cuarentena; una versión posterior válida puede recuperar una hora. No vaciar ni reconstruir tablas.
- **T07/T08:** archivo truncado completo en cuarentena cifrada, sin aplicar siquiera sus primeras filas válidas. Mes nuevo en formato existente se descubre sin cambiar código.
- **T15/T17/T18:** clasificación activa de todas las columnas nuevas; evidencia cifrada antes de SQL; roles analista y auditor sin acceso a bases de consumo/cuarentena. Ingesta sin TRUNCATE y sin modificar auditoría.
- **T19/T26:** auditoría por archivo y ejecución; errores SQL sin contenido de entrada en mensajes o logs. Los fallos de negocio se revierten antes de registrar el fallo; una caída de conexión puede impedir también auditar.
- Tres escenarios en `tests/test_batch.py` cubren lo anterior e ingieren los originales exclusivamente en una base temporal propia. Las suites S01/S02 se conservan.

## 4. Qué no haremos todavía
Sin facturación, reportes de calidad, agregación mensual, métricas contractuales ni vista analítica definitiva: corresponden a S04. `make run` conserva su rechazo explícito hasta conectar el contrato completo; S03 se ejecuta con `python -m src.batch.pipeline`.

Sin streaming, nuevas dependencias, refactorización de clientes, `src/quality/`, reintentos automáticos ni actualización de maestros existentes. Un nombre ya registrado con contenido distinto se rechaza como `changed_file`, conservando el contenido previamente aplicado. No se inventan rechazos por `calidad_lectura`.

## 5. Decisiones pendientes
A01 está aprobada internamente, sin atribuir esta interpretación a Bia. A02/A03 (contadores exactos y conflictivos y alcance del reporte) y A05 (calendario de huecos) se concretarán en S04. A04: negocio/cuarentena estables, nueva auditoría por intento. Un archivo ininterpretable o con frontera desconocida se rechaza completo; no introduce hechos parciales.

## 6. Referencias técnicas
README §4: Parte A; B1–B4 y B7; C1, C3–C5; Parte E. Pruebas T05–T12, T15, T17–T19 y T26; regresión S01/S02. Los reportes B5/B6 y §5 siguen pendientes de S04.

## 7. Archivos y responsabilidades

**Archivos que se crearán:** filas Crear. **Archivos que se modificarán:** filas Modificar. Plan reducido aprobado, sin módulos auxiliares adicionales.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/batch/__init__.py` | Identificar el paquete, sin efectos al importar. |
| Crear | `src/batch/extract.py` | Descubrir archivos y leer CSV completos. |
| Crear | `src/batch/transform.py` | Normalizar fechas/unidades y marcar B4 sin SQL. |
| Crear | `src/batch/load.py` | Maestros, precedencia, transacción por archivo y cuarentena cifrada. |
| Crear | `src/batch/pipeline.py` | Coordinar S02 y consumos; CLI de etapa y logs seguros. |
| Crear | `sql/003_consumptions.sql` | Seis tablas, claves, restricciones y permisos mínimos. |
| Crear | `tests/test_batch.py` | Tres pruebas de alto valor con PostgreSQL aislado. |
| Modificar | `src/security/classification.py` | Ampliar modelo; clientes conserva validación S02 por defecto. |
| Modificar | `data_classification.yaml` | Clasificar columnas nuevas y proteger evidencia. |
| Modificar | `src/observability.py` | Admitir filas rechazadas sin cambiar llamadas S02 existentes. |
| Modificar | `tools/manage.py` | Aplicar SQL 003 en up y declarar la tabla de consumos al preparar manifiesto. |
| Modificar | `config/pipeline.yaml` | Ruta y tamaño de lote efectivamente utilizados, sin secretos. |
| Modificar | `specs/S03-batch.md` | Alcance autorizado y criterios verificables. |
| Modificar | `specs/TRACEABILITY.md` | Evidencia de pruebas ejecutadas. |
| Modificar | `DECISIONS.md` | Modelo, A01 y límites de idempotencia. |

**Relación:** pipeline llama al servicio de clientes y a extracción/persistencia; persistencia usa transformación y seguridad. Seguridad nunca importa batch. Sin cambios en `src/client_service.py`, fachadas o pruebas existentes.

**Restricciones:** no modificar originales, credenciales, puertos, volúmenes, Makefile ni Compose. Preparación SQL administrativa separada del rol operativo; solo el hecho horario concede DELETE para A01. Sin S04/S05.
