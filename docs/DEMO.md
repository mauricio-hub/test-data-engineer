# Ensayos batch y streaming aislados

Requiere el entorno Python ya preparado y Docker Compose disponible.
El primer `demo-reset` prepara su propia llave persistente en
`%LOCALAPPDATA%\BiaEnergySecrets\demo\pii.fernet.key` en Windows (en Linux,
`${XDG_DATA_HOME:-~/.local/share}/BiaEnergySecrets/demo/pii.fernet.key`).
No lee ni genera la llave predeterminada de la base principal.
Si se define `BIA_PII_KEY_FILE`, esa configuración explícita tiene prioridad.
Una llave ausente con estado o almacenamiento demo previo bloquea la preparación;
una llave inválida nunca se reemplaza. `demo-run` solo lee la llave.
Los comandos oficiales de evaluación mantienen su comportamiento.

Desde PowerShell, en la raíz del repositorio:

```powershell
make demo-reset CONFIRM=bia-demo
make demo-run
Get-FileHash .local/demo/out/consumo_mensual.csv, .local/demo/out/dq_report.json -Algorithm SHA256
make demo-run
Get-FileHash .local/demo/out/consumo_mensual.csv, .local/demo/out/dq_report.json -Algorithm SHA256
```

El primer `demo-reset` prepara PostgreSQL 16 en el proyecto Docker `bia-demo`,
puerto `127.0.0.1:55433`, base `bia_datos`, volumen `bia-demo_pgdata`.
No levanta Redpanda. Configuración y credenciales independientes están en
`.local/demo/state.json`; no mostrar este archivo en el video ni versionarlo.
Usar su cuenta `ingesta` para DBeaver; usuario `rol_ingesta`.
No cambiar la conexión principal (`55432`).

Para grabar: reiniciar, mostrar conteos cero en DBeaver, ejecutar `demo-run`,
repetir los conteos y mostrar `analytics.v_consumo_mensual`. Ejecutar otra vez
sin reiniciar para demostrar iguales datos de negocio y hashes de salidas.
No mostrar datos originales, credenciales ni columnas personales o `payload`.

El reinicio vacía las **12 tablas de `core`**, incluyendo controles de archivos y
cuarentenas. Conserva `audit.runs`, esquemas, roles, permisos, funciones y vistas.
Elimina únicamente los tres reportes conocidos en `.local/demo/out/` para evitar
mostrar resultados antiguos. El log `.local/demo/pipeline.log` conserva intentos.
Las métricas y auditoría cambian entre ejecuciones; no comparar sus hashes.

Barreras: confirmación exacta, puerto fijo, etiquetas Docker, volumen exclusivo,
marcador privado de base e inventario exacto. TRUNCATE es transaccional, sin
CASCADE. Un bloqueo local impide dos comandos demo simultáneos. Cerrar otras
transacciones de DBeaver antes del reinicio: espera de bloqueo limitada a 3 s.
No ejecutar otros escritores manuales sobre demo durante un ensayo.
Si una interrupción deja `operation.lock`, comprobar que no hay ningún proceso
demo activo antes de retirar únicamente ese archivo manualmente.
Si se pierde `state.json`, restaurarlo; no borrar volúmenes ni rotar credenciales.

Validación opcional real (reinicia **solo demo**, lo carga dos veces y lo deja vacío):

```powershell
$env:BIA_DEMO_INTEGRATION = '1'
.\.venv\Scripts\python.exe -B -m unittest tests.test_demo -v
Remove-Item Env:BIA_DEMO_INTEGRATION
```

Sin esa variable, las pruebas de barreras no ejecutan Docker. Las pruebas de
llaves usan archivos temporales: `python -B -m unittest tests.test_keys -v`.
Los archivos bajo
`.local/` ya están excluidos de Git y de la entrega. El ZIP definitivo existente
no se actualiza automáticamente con estos cambios.

## Streaming sin reiniciar el batch

Con PostgreSQL demo ya preparado y activo, desde PowerShell:

```powershell
make demo-stream
if ($LASTEXITCODE -ne 0) { throw 'Falló streaming demo; no continuar' }
$first = (Get-FileHash .local/demo/out/alertas.json -Algorithm SHA256).Hash
make demo-stream
if ($LASTEXITCODE -ne 0) { throw 'Falló la segunda ejecución' }
if ($first -ne (Get-FileHash .local/demo/out/alertas.json -Algorithm SHA256).Hash) {
    throw 'Las alertas cambiaron entre ejecuciones'
}
```

Arranca solo Redpanda con `--no-deps`, proyecto `bia-demo`, volumen
`bia-demo_rpdata`, Kafka `127.0.0.1:19092`. Verifica identidad de PostgreSQL,
marcador de base, identidad del broker y propiedad de su volumen. No ejecuta SQL
de preparación, reinicio batch ni generación de llaves o credenciales.
Reutiliza el productor original y el consumidor con offsets finitos. Solo añade
auditoría en PostgreSQL demo. Alertas y log de streaming quedan en
`.local/demo/out/alertas.json` y `.local/demo/out/pipeline.log`.
`make stream` conserva su conexión principal y Kafka en `9092`.

Resultado esperado con los originales: 3.795 eventos y 33 alertas por ejecución
(22 fuera de banda, 6 ausencias, 5 retroactivas), sin duplicados y con igual hash.
La primera ejecución puede tardar más mientras descarga y prepara Redpanda.
Comprobar antes/después los conteos y contenido de las tablas batch desde DBeaver;
la auditoría sí debe crecer. No ejecutar `demo-reset` para validar streaming.

Pruebas unitarias sin Docker ni cambios de datos:
`python -B -m unittest tests.test_demo.DemoTests tests.test_streaming -v`.
