# Seguridad de la solución

Alcance: aplicación local Python, PostgreSQL y Redpanda. S01–S05 y las 43 pruebas fueron validadas en Windows por el responsable del proyecto. Terraform es una propuesta no desplegada; esa validación local no demuestra controles AWS.

## Datos y cifrado

- `data_classification.yaml` es política efectiva: `Classification.load()` y `validate_database()` en `src/security/classification.py` verifican etiquetas y columnas antes de escribir. Cada fase valida su ámbito.
- Todos los textos del maestro de clientes, la información privada de facturación, conceptos y evidencias de cuarentena se cifran **en Python antes de SQL**. `Cipher.seal/open` en `src/security/encryption.py` utiliza Fernet, con contexto de fila/columna autenticado dentro del mensaje. No es cifrado de disco ni una llave guardada en PostgreSQL.
- `mask_pii()` en `src/security/masking.py` detecta correos, celulares y documentos con expresiones regulares. Las observaciones enmascaradas siguen cifradas: la detección es heurística y puede omitir casos o marcar números técnicos.
- Relaciones por `cliente_id`, `frontera_id` y claves técnicas; no se descifran contactos para hacer joins. Analítica y archivos públicos no incluyen textos de clientes, pagos ni evidencia de rechazos.

## Llaves y secretos

`BIA_PII_KEY_FILE` debe señalar una llave Fernet existente fuera del repositorio. El programa no la genera ni rota silenciosamente. Si falta, es inválida o no coincide con datos existentes, la operación falla. POSIX comprueba permisos privados; Windows requiere custodiar la ACL externamente: el código no la certifica.

`tools/manage.py::prepare` genera credenciales locales nuevas para una instalación y conserva las existentes. `.local/ingesta.json` contiene solo la cuenta operativa; `.local/evaluation.json` es administrativo. SQL 001 inicializa contraseñas solo si aún no existen. El secreto heredado no está incorporado al flujo vigente. S07 añade revisión de objetos Git y exclusiones en `tools/package_delivery.py`, con pruebas en `tests/test_delivery.py`. La revisión del ZIP definitivo sigue pendiente: los escaneos de patrones/credenciales conocidas no prueban ausencia universal de secretos.

No publicar `.local/`, `.env`, llaves, estados Terraform ni `entrega.yaml` en Git. El manifiesto tiene una excepción de inclusión en el ZIP de evaluación, gestionada en S07; nunca incluye la llave PII. No imprimir archivos de credenciales para diagnosticar conexiones.

## Permisos reales

| Rol PostgreSQL | Acceso permitido | Restricción |
|---|---|---|
| `rol_ingesta` | Carga, columnas de actualización necesarias y función de auditoría | Sin propiedad/escalamiento ni TRUNCATE; DELETE solo en hechos horarios para A01 |
| `rol_analista` | `analytics.v_clientes` y `analytics.v_consumo_mensual` | Sin tablas base, PII ni escritura |
| `rol_auditor` | SELECT de `audit.runs` | Sin tablas privadas ni modificación de auditoría |

Los GRANT/REVOKE están en `sql/001_access.sql` a `sql/004_billing.sql`. `bia_owner` no inicia sesión. `audit.record_run` es SECURITY DEFINER con search_path fijo y actor tomado de `session_user`; roles operativos no pueden actualizar, borrar o truncar el registro. El superusuario conserva capacidades administrativas.

## Entradas, registros y red

Valores SQL parametrizados, nombres internos estáticos y CSV con soporte de comillas/multilínea. Nunca ejecutar texto de entradas. Los logs de `src/observability.py` y coordinadores contienen conteos, códigos y etapas; no reenviar errores del driver ni stderr del productor.

PostgreSQL escucha localmente en 55432; Redpanda anuncia IPv4 en 9092. Kafka local usa PLAINTEXT sin autenticación; no equivale a una configuración segura para una red compartida. Los eventos inválidos permanecen en Kafka; se registra ubicación técnica, no su contenido. Los originales y mensajes Kafka no son copias SQL cifradas ni quedan protegidos por Fernet automáticamente.

## Dependencias y comprobación

Cuatro dependencias directas fijadas en `requirements.txt`: PyYAML, psycopg2-binary, cryptography y kafka-python. El pinning no demuestra ausencia de vulnerabilidades; no se realizó en S06 una auditoría de CVE ni se fijaron todas las transitivas.

Ejecutar `make test` con servicios disponibles. Evidencia específica:

- `tests/test_privacy.py`: clasificación, máscaras, autenticación/contexto y mensajes sin PII.
- `tests/test_privacy_database.py`: cifrado consultado como administrador, llave incorrecta, CSV hostil y analista restringido.
- `tests/test_access.py`: permisos reales y auditoría sin UPDATE/DELETE/TRUNCATE.
- `tests/test_batch.py`, `tests/test_quality.py`: correcciones, cuarentena y errores de publicación sin filtraciones.
- `tests/test_streaming.py`: rechazo seguro, cierre y firma real de end_offsets; integración Kafka en `tests/test_streaming_integration.py`.

## Terraform: alcance y límites

`infra/main.tf` describe un bucket privado/versionado, SSE-KMS y roles por prefijo. `protected/` admite solo artefactos previamente cifrados por aplicación; `analytics/` resultados sin PII y `audit/` registros técnicos. No existe carga S3 implementada. La llave KMS no es la llave Fernet.

Ingesta lee `protected/` y escribe los tres prefijos; analista solo lee `analytics/`; auditor solo lee `audit/`. Confianza STS únicamente en ARNs de roles explícitos suministrados como variables. KMS separa Decrypt de GenerateDataKey por prefijo, exige uso mediante S3 y mantiene administración aparte. No se conceden borrado, gestión IAM ni acceso público a roles operativos.

IAM separa rutas, no inspecciona el contenido de objetos. Una integración futura tendría que garantizar que analytics/ no reciba PII y protected/ reciba ciphertext; esas cargas y controles de contenido no están implementados por este Terraform.

La bucket policy exige TLS y cabeceras explícitas SSE-KMS con el ARN exacto de la llave. La propuesta contempla PutObject simple; no pretende implementar cargas multipart. Bucket Keys deshabilitadas para conservar contexto KMS por objeto. Versionado no impide sobrescrituras ni constituye WORM; no hay CloudTrail/Object Lock ni validación de permisos AWS en vivo. Ver [THREAT_MODEL.md](THREAT_MODEL.md) y [RUNBOOK.md](RUNBOOK.md).

Referencias cloud: [SSE-KMS y permisos requeridos](https://docs.aws.amazon.com/AmazonS3/latest/userguide/UsingKMSEncryption.html), [cambio de contexto al usar Bucket Keys](https://docs.aws.amazon.com/AmazonS3/latest/userguide/bucket-key.html). Son fundamentos del diseño, no evidencia de un despliegue.
