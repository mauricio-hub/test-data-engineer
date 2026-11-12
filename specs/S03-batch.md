# S03 — Ingesta y correcciones de consumos

Estado: propuesto. Fase 3 no autorizada. Depende de S02.

## 1. Objetivo
Cargar archivos de consumo, incorporar correcciones y repetir la ejecución sin duplicar datos ni dañar lo ya cargado.

## 2. Qué vamos a construir
- Descubrir archivos por directorio y reconocer formatos por contenido y cabecera, sin una lista de meses.
- Leer registros CSV completos; convertir fechas a `America/Bogota` y números con `Decimal`, aritmética decimal. Convertir MWh a kWh multiplicando por 1.000 en cada fila.
- Modelar clientes, fronteras, límites y consumos, con una lectura única por `(frontera_id, timestamp)`.
- Guardar versión, nombre de archivo y posición de fila para decidir qué lectura gana. Registrar contenido y estado de cada archivo.
- Aplicar cada archivo mediante una transacción: confirmar todos sus cambios o deshacerlos si falla.

## 3. Cómo sabemos que funciona
- **T09/T10:** se reconocen los formatos existentes, decimal con coma y fechas UTC que cambian de mes al convertir a hora local. El lector no se elige por mes.
- **T11:** gana la mayor versión; en empate, la última fila siguiendo nombres de archivo en orden lexicográfico. Un archivo anterior en ese orden no gana por llegar después.
- **T12:** nulos, vacíos, negativos y valores mayores de 1.000.000 kWh se rechazan; cero y exactamente 1.000.000 son válidos. El orden de selección y validación sigue A01 una vez aprobado.
- **T05/T06:** repetir no duplica datos ni cuarentena. Una corrección cambia solo las claves afectadas y no se revierte al reprocesar originales; no se vacían ni reconstruyen todas las tablas.
- **T07/T08:** un archivo estructuralmente corrupto se rechaza completo sin cambiar datos previos. El motivo y la evidencia protegida son consultables. Los rechazos B4 pueden conservarse por fila.
- **T08:** un mes sintético en formato conocido se incorpora sin cambiar código. Las pruebas usan un directorio temporal, no modifican originales.
- **T19:** cada intento registra identidad técnica, acción, tiempos, conteos y resultado, también al fallar, sin datos personales. El resultado se conserva aunque se deshaga la transacción de negocio.
- Un fallo de infraestructura termina con error. Ante un archivo rechazado, la propuesta es continuar con otros y terminar con éxito solo si se preserva la integridad, dejando el rechazo explícito.

## 4. Qué no haremos todavía
No inventar rechazos por `calidad_lectura`. No admitir cambios de contenido bajo un mismo nombre sin acordar una política: los originales son inmutables. No desarrollar aún las salidas de S04.

## 5. Decisiones pendientes
Resolver A01–A05: validación, duplicados, contadores, idempotencia y calendario de huecos.

## 6. Referencias técnicas
- README §4: Parte A, B1–B4, B7 y C5.
- Pruebas: T05–T12 y T19.

## 7. Archivos y responsabilidades

**Responsable de ETL:** S03 crea extracción, transformación, persistencia, coordinación batch y validación de calidad. Reutiliza seguridad y observabilidad de S02. Mantener la secuencia S03 → S04 → S05.

**Archivos que se crearán:** filas «Crear». **Archivos que se modificarán:** filas «Modificar». `src/batch/` y `src/quality/` todavía no existen y se crean aquí; los módulos de seguridad y el servicio de clientes deben venir de S02 aprobado y verificado.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/batch/__init__.py` | Documentar la interfaz mínima de batch, sin ejecutar procesos al importar. |
| Crear | `src/batch/extract.py` | Recibir la lectura/parser de clientes del servicio y añadir descubrimiento y lectura de consumos y maestros pendientes. |
| Crear | `src/batch/transform.py` | Recibir la protección de filas de clientes y añadir normalización de hora, unidades, decimales y precedencia, sin SQL. |
| Crear | `src/batch/load.py` | Recibir conexión/persistencia de clientes y aplicar cargas de consumo, versiones, transacciones y cuarentena. |
| Crear | `src/batch/pipeline.py` | Coordinar clientes y consumos usando componentes compartidos, sin concentrar reglas de datos. |
| Crear | `src/quality/__init__.py` | Documentar la interfaz mínima de calidad; los reportes se crearán en S04. |
| Crear | `src/quality/validators.py` | Recibir controles semánticos de clientes y añadir B4/rechazos técnicos, separados de lectura y persistencia. |
| Crear | `sql/003_consumptions.sql` | Definir fronteras/límites, hechos horarios, procedencia, registro de archivos, cuarentena y permisos específicos. |
| Crear | `tests/test_batch.py` | Comprobar formatos, normalización, validación y precedencia con casos pequeños. |
| Crear | `tests/test_batch_database.py` | Probar idempotencia, correcciones incrementales, mes nuevo y corrupción con PostgreSQL real aislado. |
| Crear | `tests/db_helpers.py` | Compartir recursos temporales y conexiones entre suites de base, sin otro sistema de preparación. |
| Modificar | `src/client_service.py` | Delegar lectura, transformación, validación y carga en los componentes recién creados, conservando su interfaz y sin duplicar funciones. |
| Modificar | `src/security/classification.py` | Extender el contrato al esquema nuevo y su cuarentena, sin reimplementar cifrado. |
| Modificar | `data_classification.yaml` | Clasificar todas las columnas nuevas junto con el cambio SQL. |
| Modificar | `src/observability.py` | Ampliar eventos y conteos permitidos de etapas, sin filas ni PII. |
| Modificar | `tools/manage.py` | Registrar SQL y nombres del manifiesto; no introducir ETL aquí. |
| Modificar | `config/pipeline.yaml` | Conectar opciones existentes de rutas/procesamiento a su uso efectivo, sin secretos. |
| Modificar | `tests/test_privacy.py` | Mantener los casos S02 y adaptar solo los puntos internos de llamada que cambien con la extracción. |
| Modificar | `tests/test_privacy_database.py` | Reutilizar el auxiliar común sin cambiar las garantías de privacidad S02. |
| Modificar | `specs/S03-batch.md` | Registrar interpretaciones aprobadas y aceptación real. |
| Modificar | `specs/TRACEABILITY.md` | Registrar cobertura y resultados de batch. |
| Modificar | `DECISIONS.md` | Completar precedencia, aislamiento y esquema aprobado. |

**Responsabilidades y relación:** el coordinador batch usa el servicio de clientes y los componentes de consumo. El servicio de clientes usa extracción, transformación, carga y validadores; nunca importa `src/batch/pipeline.py`. Los componentes batch no importan el servicio ni las fachadas. Validadores y seguridad no importan coordinadores. Esta dirección evita el ciclo servicio → pipeline → servicio.

Al trasladar una función de `src/client_service.py`, su implementación anterior se sustituye por delegación; no se mantiene una segunda versión. Conservar las fachadas `src/clients.py` y `src/privacy.py` sin modificar sus contratos. La preparación SQL sigue separada de la cuenta operativa.

**Restricciones:** no crear otros cifradores, máscaras, productores o sistemas de conexiones. No cambiar `data/`, puertos, credenciales, volúmenes o Makefile. Reutilizar auditoría S01 y garantías de clientes S02 sin ampliar sus permisos. `make run` no debe declarar completo el contrato mientras falten salidas de S04; la conexión final de ese comando se mantiene en S04.

**Pruebas:** `tests/test_batch.py` cubre T09–T12 y validadores; `tests/test_batch_database.py` cubre T05–T08/T19 y relaciones T04. Repetir todas las suites S01/S02, incluyendo fachadas y CLI. Fixtures fuera de `data/` y únicamente recursos temporales propios. El auxiliar común se justifica por dos suites de integración, sin copiar su lógica.

**Decisiones pendientes adicionales:** aprobar esquema exacto, interfaces de registros normalizados y traslado de responsabilidades desde el servicio de clientes. La tabla no resuelve A01–A05 ni autoriza crear módulos antes de aprobar S03. S04 conserva reportes y facturación; S05 conserva streaming.
