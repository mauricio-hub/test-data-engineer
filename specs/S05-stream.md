# S05 — Consumo de eventos con finalización automática

Estado: propuesto. Fase 5 no autorizada. Depende de S01.

## 1. Objetivo
Leer mediciones desde Redpanda mediante Kafka, generar las tres alertas exigidas y terminar dentro del tiempo disponible.

## 2. Qué vamos a construir
- Publicar en `mediciones.raw` con `tools/producer.py` y consumir realmente desde Kafka.
- Capturar posiciones iniciales y finales por partición, llamadas offsets: delimitan qué mensajes pertenecen a esta reproducción. Tomar el inicio antes de publicar y el final después de confirmar la publicación.
- Consumir ese rango sin cantidad fija y conservando el orden por frontera.
- Detectar lecturas retroactivas al recibirlas, sin ordenar previamente por hora de medición. Calcular ausencias al cierre solo si se aprueba A07.

## 3. Cómo sabemos que funciona
- **T22:** `kwh > max_kwh` genera `CONSUMO_FUERA_DE_BANDA` con `ts_medicion`. La igualdad no alerta; no se añade alerta por mínimo.
- **T23:** una fecha/hora menor al máximo previo de esa frontera genera `LECTURA_RETROACTIVA` con la hora de la lectura tardía. La igualdad no alerta y una lectura tardía no reduce el máximo.
- **T24:** se usa la rejilla de 96 intervalos desde `2026-06-01T00:00:00-05:00`. Tres ausencias consecutivas generan `FRONTERA_SIN_REPORTE` en el tercer intervalo; solo una alerta hasta la recuperación. Se prueban comienzo/final del día, dos ausencias, recuperación y llegada tardía según A07.
- **T25:** se procesan todos los eventos del archivo, incluidos los 3.795 observados, sin fijar ese número en código. Repetir excluye mensajes de reproducciones anteriores.
- **T32:** `out/alertas.json` es una lista de objetos con `tipo`, `frontera_id` y `ts` en ISO 8601 con desplazamiento horario explícito. No se repite la combinación `(tipo, frontera_id, ts)`.
- **T31:** `make stream` termina solo en menos de 300 segundos. Un fallo de Redpanda, del productor o un consumo incompleto devuelve error; no simula éxito mediante una salida vacía.

## 4. Qué no haremos todavía
No prometer procesamiento distribuido exactamente una vez ni alertas inmediatas con A07. Si Bia exige detección inmediata durante la llegada, revisar este spec antes de implementar.

## 5. Decisiones pendientes
Resolver A07 —ausencias y lecturas tardías— y A08 —cantidad, fechas y aislamiento de reproducciones—. Bloquean el algoritmo de ausencia.

## 6. Referencias técnicas
- README §4: Parte D, tres reglas de alerta y rejilla; §5: finalización y `out/alertas.json`.
- Pruebas: T22–T25, T31 y T32.

## 7. Archivos y responsabilidades

**Archivos que se crearán:** filas «Crear». **Archivos que se modificarán:** filas «Modificar». El productor existente se reutiliza sin crear una copia.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/streaming/__init__.py` | Documentar la interfaz mínima de streaming, sin conexiones al importar. |
| Crear | `src/streaming/consumer.py` | Coordinar productor existente, límites de offsets, consumo Kafka y finalización; delegar reglas de alerta. |
| Crear | `src/streaming/alerts.py` | Aplicar las tres reglas y mantener estado por frontera sin depender del cliente Kafka. |
| Crear | `tests/test_streaming.py` | Probar banda, retroactividad, ausencias, recuperación y deduplicación con eventos sintéticos. |
| Crear | `tests/test_streaming_integration.py` | Verificar reproducción por Kafka real, aislamiento de ejecuciones y salida dentro del tiempo. |
| Modificar | `tools/manage.py` | Dirigir `stream` al consumidor con el mismo comando Make; no alojar reglas de alerta. |
| Modificar | `requirements.txt` | Incorporar la dependencia Kafka necesaria para consumidor y productor suministrado, revisando su versión. |
| Modificar | `src/observability.py` | Añadir eventos y conteos permitidos de streaming sin registrar mensajes crudos. |
| Modificar | `specs/S05-stream.md` | Registrar política aprobada de ausencias y finalización. |
| Modificar | `specs/TRACEABILITY.md` | Registrar casos de alerta y evidencia de Kafka real. |
| Modificar | `DECISIONS.md` | Cerrar ADR-006 con la semántica que se apruebe. |

**Responsabilidades y relación:** `consumer.py` invoca el único `tools/producer.py`, recibe mensajes y llama a `alerts.py`. Reutiliza el escritor JSON atómico de `src/quality/reports.py` de S04 y los eventos seguros de `src/observability.py`; no copia esos mecanismos. Si se implementa S05 antes de S04, debe aprobarse otra secuencia o extraer antes ese escritor, no crear uno paralelo.

**Restricciones:** no crear `src/streaming/producer.py`, no modificar el productor original ni `data/eventos/mediciones_stream.ndjson`. Conservar tópico `mediciones.raw`, puertos y nombres Make. No cambiar tablas o roles para estas alertas de archivo. Las reglas de alerta no dependen de cifrado, SQL ni del reloj real para decidir el tiempo de medición.

**Pruebas:** `tests/test_streaming.py` cubre T22–T24/T32; `tests/test_streaming_integration.py` cubre T25/T31/T32. `out/alertas.json` se genera durante la ejecución; no se crea como fixture de entrega.

**Decisiones pendientes adicionales:** además de A07/A08, aprobar las interfaces de estado/evento y la dependencia del escritor de S04. La dependencia funcional de S01 se conserva; la organización propuesta añade reutilización de un componente de S04 y requiere confirmar esa secuencia.
