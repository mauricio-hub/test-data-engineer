# S05 — Streaming con finalización automática

Estado: plan reducido y A07/A08 aprobados por el usuario. Implementado; integración real pendiente de instalar la dependencia en este entorno.

## 1. Objetivo
Consumir una reproducción finita desde Redpanda, generar las tres alertas exactas y terminar sin dejar procesos colgados.

## 2. Qué vamos a construir
- Usar el productor original para `mediciones.raw`, capturando offsets por partición antes/después. Crear el tópico solo si falta, sin borrar históricos ni modificar particiones existentes.
- Comprobar cantidad publicada frente a registros no vacíos del archivo, calculada dinámicamente. Consumir solo ese rango, con asignación manual y sin commits de grupos.
- Evaluar banda y retroactividad en orden Kafka por frontera. Evaluar ausencias al finalizar con todos los eventos válidos.
- Publicar `out/alertas.json` completo, logs seguros y auditoría con operación stream. Mantener métricas batch existentes sin sobrescribirlas.

## 3. Cómo sabemos que funciona
- **T22:** kWh estrictamente mayor que máximo; igualdad no alerta, sin regla por mínimo.
- **T23:** timestamp menor al máximo anterior genera retroactividad; igualdad no. Una lectura tardía no reduce el máximo.
- **T24/A07:** rejilla de 96 intervalos desde `2026-06-01T00:00:00-05:00`. Alertar exactamente en el tercero ausente, una vez por racha, reiniciando al recuperar una medición. Incluir comienzo/final y presencia tardía. Ejemplos: faltan 00:00/00:15/00:30 → alerta 00:30; faltan 23:15/23:30/23:45 → alerta 23:45.
- **T25/A08:** procesar todos los eventos reales, sin número fijo; reejecutar excluye reproducciones previas. Idempotencia de alertas, no del histórico Kafka, que crece con cada publicación.
- **T32:** lista de objetos únicamente con `tipo`, `frontera_id`, `ts`; ISO 8601 con offset. Sin duplicados por esos tres campos, orden estable.
- **T26:** no escribir mensajes crudos, medidor ni excepciones externas en logs. Validar frontera conocida, JSON, timestamp con zona y en rejilla, y número finito. B4 de batch no se extiende a streaming.
- Un evento inválido conserva su mensaje en Kafka y registra partición/offset; termina con error sin publicar una lista incompleta.
- **T31:** plazo interno de 250 s, productor hasta 120 s dentro de ese plazo y comando supervisor hasta 280 s. Timeouts, cierre en finally y captura de stderr del productor. Broker/productor/rango incompleto/publicación fallidos retornan error.
- Dos escenarios unitarios y una integración real en tópico temporal propio; repetir las 40 pruebas existentes.

## 4. Qué no haremos todavía
Sin detección inmediata de ausencia, ejecución continua, procesamiento distribuido exactamente una vez, nuevas tablas, permisos, cifradores o productor alternativo. Sin modificar datos, volúmenes, credenciales, puertos, Makefile ni Compose.

Limitaciones: usar un solo productor durante el rango capturado; conteos detectan interferencia habitual, no autentican pertenencia a la reproducción. No admitir eventos fuera de la rejilla definida sin revisar el contrato. Kafka crece por cada reproducción. Publicación y auditoría no forman una transacción conjunta; un fallo administrativo posterior puede dejar archivo completo y retorno de error. La auditoría del fallo necesita PostgreSQL disponible.

## 5. Decisiones pendientes
A07/A08 aprobadas internamente, sin confirmación adicional de Bia. Validar productor/consumidor en Redpanda real y `make stream` local una vez instalada la dependencia. La lectura directa del archivo es referencia del algoritmo, nunca evidencia de consumo Kafka.

## 6. Referencias técnicas
README §4 Parte D y C5/E; §5 `make stream` (<300 s) y contrato de `alertas.json`. T22–T26/T31/T32. Dependencia única añadida: [kafka-python 2.3.2](https://pypi.org/project/kafka-python/2.3.2/), la misma biblioteca requerida por el productor original.

## 7. Archivos y responsabilidades

**Crear:** filas Crear. **Modificar:** filas Modificar.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/streaming/__init__.py` | Paquete sin conexiones al importar. |
| Crear | `src/streaming/alerts.py` | Validación y tres reglas, sin Kafka/SQL. |
| Crear | `src/streaming/consumer.py` | Maestros, productor, offsets, consumo, cierre, auditoría y salida. |
| Crear | `tests/test_streaming.py` | Reglas y fallos controlados: dos escenarios. |
| Crear | `tests/test_streaming_integration.py` | Productor original y Redpanda real dos veces: un escenario. |
| Modificar | `tools/manage.py` | Dirigir stream al módulo y propagar retorno con timeout. |
| Modificar | `requirements.txt` | Fijar la única dependencia Kafka. |
| Modificar | `tests/test_setup.py` | Ampliación autorizada posteriormente: añadir solo kafka-python a la lista esperada. |
| Modificar | `src/observability.py` | Eventos seguros y operación stream; batch conserva su valor por defecto. |
| Modificar | `src/quality/reports.py` | Extraer escritor existente a publish_files; publish S04 conserva interfaz y algoritmo. |
| Modificar | `specs/S05-stream.md` | Alcance y limitaciones. |
| Modificar | `specs/AMBIGUITIES.md` | Registrar aprobación A07/A08. |
| Modificar | `specs/TRACEABILITY.md` | Evidencias y comprobaciones pendientes. |
| Modificar | `DECISIONS.md` | Concretar ADR-006. |

**Relación:** consumer llama al productor original, alerts, escritor S04 y auditoría existente. Alerts no importa coordinadores. Sin módulos auxiliares adicionales.

**Pruebas:** integración usa tópico con UUID y elimina exclusivamente ese recurso propio; nunca elimina mediciones.raw. Si falta kafka-python, queda omitida explícitamente, no aprobada; si la dependencia está instalada y Redpanda falla, la prueba falla.
