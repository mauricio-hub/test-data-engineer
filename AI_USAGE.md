# Uso de IA en la prueba

## Herramientas y revisión humana

Se utilizó Codex para analizar README/specs, proponer arquitectura, redactar Python/SQL, ejecutar herramientas locales y preparar documentación. Se consultaron documentación oficial de Kafka, AWS y Terraform mediante búsqueda web. No se midió un porcentaje fiable de código generado y no se afirma uno.

El responsable aprobó fases, resolvió interpretaciones, pidió reducir refactorizaciones, diagnosticó diferencias de conexión en Windows y verificó el sistema real. Los comandos y resultados de Windows fueron comunicados por él; no se atribuyen a ejecuciones de la IA. Los cambios de código motivados por esa revisión fueron implementados con asistencia de IA.

## Tres prompts reales

Extractos textuales de instrucciones del responsable en esta conversación, sin datos personales:

> Mantén la interpretación A01 ya acordada: si gana una corrección inválida, se conserva su precedencia, se registra el rechazo y no queda una lectura válida vigente.

Resultado: estado de precedencia separado del hecho válido; una corrección inválida deja hueco y una versión inferior no restaura la lectura. Se verificó en `tests/test_batch.py`.

> S02 debe centrarse exclusivamente en seguridad, privacidad, clientes y observabilidad.

Resultado: fachadas compatibles y servicio de clientes conservado; batch se implementó en S03. El responsable rechazó una reorganización más amplia antes de programar.

> Autorizo cambiar únicamente el valor predeterminado de bootstrap a "127.0.0.1:9092", manteniendo la configuración externa y las demás garantías de S05.

Resultado: corregir bootstrap mostró que el líder seguía anunciando localhost. Las consultas de solo lectura aislaron el problema IPv6 y motivaron la posterior excepción explícita para anunciar IPv4 en Compose, sin modificar el productor original.

## Qué cambió por revisión humana

- `src/client_service.py` no se extrajo a múltiples capas en S03: se conservó el flujo validado y se añadieron solo los módulos necesarios de consumo.
- A01 fue una interpretación aprobada, no un requisito atribuido a Bia. A02–A08 también quedaron explícitas antes de implementarlas.
- La validación inicial con mocks no se aceptó como prueba Kafka: el responsable ejecutó productor/consumidor reales y aportó fallos de Windows hasta completar la integración.

## Un error concreto de la IA

En `src/streaming/consumer.py:152` y `:158`, la IA introdujo `end_offsets(parts, timeout_ms=5000)`. La API instalada de kafka-python 2.3.2 admite `end_offsets(parts)` y usa `request_timeout_ms` del consumidor. El argumento provocaba TypeError, oculto como `broker_error`.

El responsable detectó el fallo de integración; se inspeccionó la firma real y se corrigieron ambas llamadas. `tests/test_streaming.py::test_02_T25_T26_T31_failures_offsets_timeout_and_publication` usa ahora `create_autospec(ConsumerAPI, instance=True)` y comprueba las dos llamadas sin keyword incompatible. El mock genérico anterior aceptaba la llamada errónea y no detectaba el defecto.

Otro aprendizaje real: cambiar bootstrap no cambia los advertised listeners. Se preservó el productor suministrado y se autorizó explícitamente modificar solo la dirección externa anunciada. La primera integración omitida por dependencia ausente nunca se declaró aprobada.

## Límites y evidencia

No se delegaron decisiones de negocio, aprobación de alcance ni aceptación final. No se fabricaron ejecuciones AWS, porcentajes, resultados de seguridad o historial Git. El responsable confirmó S01–S05, 43 pruebas aprobadas y dos replays idénticos de 3.795 eventos/33 alertas. Terraform y documentación corresponden a S06; validación final del paquete sigue en S07.
