# Operación local de Bia Energy

## Ejecución normal

Desde la raíz del repositorio, con Python >=3.11, GNU Make y Docker Compose v2:

```powershell
make setup
make up
# BIA_PII_KEY_FILE debe estar configurada con la llave externa existente.
make run
make run
make stream
make test
make verificar
make down
```

`make setup` no genera la llave PII; no sustituir una llave usada para datos existentes. Configurar la variable sin imprimir su contenido ni publicar la ubicación privada. En PowerShell puede asignarse desde una ruta elegida por el operador: `$env:BIA_PII_KEY_FILE = Read-Host 'Ruta de la llave externa existente'`. Custodiar su ACL; para una instalación nueva usar el procedimiento explícito de [docs/S02.md](docs/S02.md), nunca regenerarla para resolver un error de descifrado.

PostgreSQL local: `127.0.0.1:55432`; Kafka: `127.0.0.1:9092`. Salidas: CSV mensual, DQ, métricas y alertas en `out/`; logs JSON en `logs/pipeline.log`. Límites: batch 900 s, streaming 300 s. Validación confirmada en Windows: 43 pruebas; streaming 3.795 eventos y 33 alertas (22 banda, 6 ausencia, 5 retroactividad). Son resultados del paquete original, no constantes del algoritmo.

## Diagnóstico seguro

| Síntoma | Revisar | Acción |
|---|---|---|
| `key_missing`, `key_invalid`, `cipher_invalid` | Variable, archivo externo, permisos y llave correcta | Detener carga; recuperar la llave autorizada, no reemplazarla |
| Fallo PostgreSQL | Servicio/puerto 55432 y configuración local existente | Conservar credenciales y volumen; no intervenir el PostgreSQL de otro proyecto en 5432 |
| `broker_error` | Campo `stage` del evento de streaming | Distinguir conexión, metadatos, creación y offsets; no aumentar timeouts a ciegas |
| Más cuarentena o `changed_file` | Motivo y metadatos de archivo/fila | Preservar fuente; revisar con permisos autorizados sin imprimir payload descifrado |
| Error de publicación | Acceso/escritura en `out/` y espacio disponible | Corregir causa y reejecutar; archivos individuales completos pueden pertenecer a intentos distintos |

Puede inspeccionarse la última línea con `Get-Content .\logs\pipeline.log -Tail 1`. No copiar archivos de credenciales, llaves o datos originales al chat/incidencias. Los logs no contienen la excepción externa completa deliberadamente.

## Recuperación

**Fallo parcial de batch:** reejecutar `make run` tras corregir la causa. Cada archivo se confirma completo; archivos ya aplicados y cuarentena no se duplican. Auditoría/logs sí crecen. Regenerar salidas no depende de conservar el `out/` anterior.

**Corrección tardía:** incorporar un archivo nuevo por el canal autorizado, sin editar originales. Mayor versión gana; empate por nombre/fila. A01: ganador inválido retira el hecho y deja hueco. La misma versión antigua no lo recupera. Un nombre existente con contenido distinto se rechaza; no forzar su hash ni borrar el registro para aceptarlo.

**Rechazos elevados:** comparar motivos de `dq_report.json` (conjunto aceptado) y `metrics.json` (trabajo del intento). Un archivo rechazado completo no aporta meses al calendario. No imputar lecturas ni relajar reglas para cuadrar conteos. Si una fuente aceptada falta o cambia, recuperar la copia autorizada: no inventar su contenido para regenerar DQ.

**Streaming:** no ejecutar otro productor simultáneamente. `make stream` invoca el original y delimita su replay por offsets. Repetir debe dar el mismo `alertas.json`, aunque Kafka acumule publicaciones. Evento inválido: revisar partición/offset bajo autorización; permanece en Kafka y el comando falla sin publicar una lista parcial.

Si el broker aún anuncia localhost, aplicar la configuración existente recreando solo Redpanda y reutilizando su volumen:

```powershell
docker compose --project-name bia-evaluation --env-file .local/compose.env -f docker-compose.yml up -d --no-deps --force-recreate --wait --wait-timeout 120 redpanda
```

No resolver fallos con `down -v`, borrado de datos o regeneración de credenciales. `make down` conserva volúmenes.

**Sospecha de acceso indebido:** detener las ejecuciones afectadas, restringir el acceso local con el responsable del entorno, preservar evidencia técnica y registrar tiempos/operaciones sin payloads. Informar al responsable real del proyecto; no hay contactos ni guardia inventados. No eliminar registros ni efectuar una rotación improvisada: una llave comprometida requiere plan explícito de recifrado y recuperación.

## Terraform y pendientes

Solo revisión local, sin cuenta AWS:

```powershell
terraform -chdir=infra fmt -check
terraform -chdir=infra init -backend=false -input=false
terraform -chdir=infra validate
```

No ejecutar plan/apply. Init descarga el proveedor y genera lockfile/caché; no crea recursos AWS. El responsable confirmó validate satisfactorio con Terraform 1.17.1 en Windows; el lockfile está versionado. Registrar fmt/validate del cierre sin confundir esta evidencia con un despliegue. Variables de confianza/nombre son obligatorias para cualquier uso futuro; no crear archivos con cuentas reales en Git. La política S3 descrita requiere cabeceras de cifrado y llave explícitas; no existe integración S3 en el programa.

Alcance de la comprobación: [terraform validate](https://developer.hashicorp.com/terraform/cli/commands/validate) revisa consistencia y esquema, no servicios remotos ni autorización efectiva en AWS.

El generador conserva faltantes concretos y ya no restaura la declaración antigua de fases pendientes. Completar candidato y ejecutar el recorrido final con `make verificar` antes de autorizar el paquete. El empaquetador `tools/package_delivery.py` no reemplaza esa verificación, no crea commits ni sobrescribe paquetes. El ZIP definitivo, video y `make down` siguen pendientes de autorización; las pruebas de empaquetado usan solo archivos temporales.
