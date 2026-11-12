# Guía sencilla del repositorio

Este proyecto debe convertir archivos de consumo eléctrico en información confiable y protegida. Esta guía explica para qué sirve cada parte, sin necesidad de conocer todo el código.

**Contexto de esta guía:** describe la estructura al cierre de S01. Ahora también se implementó S02: carga protegida de clientes, `src/`, clasificación y esquema correspondiente. Para el estado y comandos actuales consulta [S02.md](S02.md). Consumos y alertas siguen pendientes; Docker aún requiere validación local. Los apartados siguientes conservan la explicación de S01.

## 1. El mapa general

```text
prueba-tecnica/
├── README.md                 Requisitos originales de Bia
├── AGENTS.md                 Reglas para trabajar en este repositorio
├── DECISIONS.md              Decisiones de arquitectura y su estado
├── Makefile                  Atajos para ejecutar comandos
├── docker-compose.yml        Servicios locales: PostgreSQL y Redpanda
├── requirements.txt          Librerías de Python necesarias
├── entrega.example.yaml      Modelo de entrega sin contraseñas
├── entrega.yaml              Datos de conexión para el evaluador
├── .env.example              Ejemplo de opciones del entorno
├── .gitignore                Archivos que Git debe ignorar
├── config/                   Configuración del proceso
├── tools/                    Programas auxiliares
├── sql/                      Instrucciones para PostgreSQL
├── tests/                    Pruebas automáticas
├── data/                     Archivos originales de Bia: no modificar
├── specs/                    Qué debe hacer cada funcionalidad
├── docs/                     Guías y evidencia del trabajo
└── plantillas/               Modelos para la documentación final
```

También hay carpetas generadas localmente, como `.venv/` y `.local/`. Las explicamos más adelante.

## 2. Los archivos de la raíz

### `README.md`: el enunciado de Bia

Es nuestra fuente de requisitos. Explica qué construir, cómo se evalúa, qué archivos entregar y qué errores eliminan al candidato.

Si queremos saber **qué exige la prueba**, empezamos aquí.

### `AGENTS.md`: nuestras reglas de trabajo

Indica cómo debe trabajar el asistente dentro del repositorio: no modificar datos originales, no exponer información personal y esperar aprobación antes de implementar otra fase.

No prepara servicios ni ejecuta código. Es una guía de conducta para el trabajo.

### `DECISIONS.md`: por qué elegimos una solución

Registra alternativas, decisiones y consecuencias. Por ejemplo, por qué separar al propietario de las tablas de los usuarios que las consultan.

Una decisión puede estar propuesta, aprobada o implementada. Esos estados no significan lo mismo. Los registros de decisiones se llaman **ADR**.

### `Makefile`: los atajos de ejecución

Evita recordar comandos largos. Por ejemplo, `make up` llama al programa que prepara los servicios.

Los nombres importan porque el evaluador ejecutará esos mismos comandos:

- `make setup`: prepara Python, instala dependencias y genera credenciales locales.
- `make up`: levanta servicios, espera disponibilidad y prepara permisos y auditoría.
- `make test`: ejecuta las pruebas actuales.
- `make down`: detiene servicios sin borrar sus datos.
- `make verificar`: ejecuta el verificador suministrado por Bia.
- `make run`: cargará y procesará los datos; todavía devuelve error porque está pendiente.
- `make stream`: procesará eventos y alertas; todavía devuelve error.
- `make clean`: limpieza pendiente; actualmente devuelve error para evitar borrados accidentales.

Tener estos comandos escritos no demuestra que hayan pasado: la evidencia real está en `docs/S01.md`.

### `docker-compose.yml`: los servicios locales

Describe dos servicios que Docker debe ejecutar de forma aislada:

- **PostgreSQL:** la base de datos donde guardaremos información organizada y el registro de auditoría.
- **Redpanda:** recibe y entrega eventos usando el protocolo Kafka; lo usaremos para mediciones que llegan como mensajes.

Define versiones, puertos, almacenamiento persistente y comprobaciones de disponibilidad. No transforma los archivos de consumo por sí solo.

El almacenamiento persistente de Docker se llama **volumen**: conserva los datos aunque detengamos un contenedor. Por eso `make down` no equivale a borrar la base.

### `requirements.txt`: las librerías de Python

Lista paquetes externos y sus versiones:

- `PyYAML`: permite leer archivos YAML, usados para configuración y entrega.
- `psycopg2-binary`: permite conectar Python con PostgreSQL; lo requiere el verificador de Bia.

Es una lista para instalar, no un programa. La instalación y auditoría automática siguen bloqueadas en el entorno de esta sesión.

### `entrega.example.yaml` y `entrega.yaml`

El primero es una plantilla sin contraseñas. El segundo le dice al evaluador cómo conectarse y qué objetos revisar.

`make setup` genera el manifiesto local con credenciales nuevas. Aunque el archivo generado tiene extensión `.yaml`, su contenido usa JSON, que el lector YAML suministrado también acepta.

**No compartas su contenido sin revisarlo:** contiene contraseñas locales. Los datos del candidato y los objetos de negocio aún tienen campos pendientes.

### `.env.example` y `.gitignore`

- `.env.example` muestra opciones como el puerto de PostgreSQL. No contiene contraseñas reales ni es obligatorio copiarlo: la preparación usa `.local/`.
- `.gitignore` indica qué archivos generados o sensibles no deben añadirse normalmente a Git, como entornos Python y credenciales. No borra archivos ni elimina secretos que ya estuvieran en un historial.

Git es la herramienta que registra versiones y cambios. Esta copia no tenía un repositorio Git y no hemos creado uno.

## 3. `tools/`: programas auxiliares

**Tools significa herramientas.** Esta carpeta contiene programas de apoyo para preparar o comprobar el proyecto. No es todavía el pipeline que transforma consumos.

### `tools/manage.py`

Es el encargado de preparar y administrar el entorno de S01:

- Crea el entorno Python e instala las dependencias con `setup`.
- Genera o conserva credenciales con `prepare`, utilizado internamente durante la preparación.
- Genera los archivos locales y el manifiesto de entrega.
- Levanta y comprueba servicios con `up`.
- Aplica `sql/001_access.sql` para preparar permisos y auditoría.
- Detiene servicios con `down`.

Si encuentra un error, devuelve un resultado de fallo sin imprimir contraseñas. No lee los consumos originales ni genera una llave de cifrado de datos personales.

### `tools/producer.py`

Lo suministró Bia. Lee `data/eventos/mediciones_stream.ndjson` y envía sus mediciones a Redpanda, al tópico `mediciones.raw`.

Un **tópico** es un canal de mensajes. El productor envía mensajes; el futuro consumidor los recibirá y evaluará las alertas.

Este programa no genera las alertas. Su integración y la dependencia `kafka-python` siguen pendientes de S05.

### `tools/verificar_entrega.py`

También lo suministró Bia. Lee `entrega.yaml`, intenta conectarse con las cuentas declaradas y busca los objetos indicados.

Sirve para detectar nombres o credenciales inconsistentes. **No certifica que el cifrado o los permisos sean seguros**: eso requiere pruebas específicas.

## 4. `sql/`: instrucciones para la base de datos

SQL es el lenguaje con el que definimos y consultamos objetos en PostgreSQL.

### `sql/001_access.sql`

Prepara los esquemas, roles y registro de auditoría. Un **esquema** agrupa objetos dentro de una base, como una carpeta lógica.

- `core`: reservado para las futuras tablas de negocio.
- `analytics`: reservado para consultas analíticas autorizadas.
- `audit`: contiene el registro de auditoría.

Define estas cuentas:

- `bia_owner`: propietario de objetos, sin inicio de sesión.
- `rol_ingesta`: cuenta operativa para cargar datos; actualmente puede registrar ejecuciones.
- `rol_analista`: tendrá acceso a la vista analítica, todavía pendiente.
- `rol_auditor`: puede consultar el registro de auditoría.

`audit.runs` guarda quién ejecutó una operación, cuándo, cuántas filas procesó y el resultado. `audit.record_run` es la función autorizada para añadir una entrada sin permitir cambiar el actor ni modificar entradas anteriores.

Los roles operativos no pueden actualizar, borrar, vaciar ni alterar ese registro. Esto no prohíbe las actualizaciones de negocio necesarias para corregir consumos.

## 5. `tests/`: comprobaciones automáticas

### `tests/test_setup.py`

Prueba la preparación sin necesitar servicios externos. Comprueba, entre otras cosas, que repetir conserve las credenciales, que el manifiesto coincida y que un error no muestre secretos.

### `tests/test_access.py`

Necesita PostgreSQL accesible. Abre conexiones reales y prueba lo permitido y lo prohibido para cada rol.

Crea una tabla y una vista sintéticas, las usa para comprobar permisos y las elimina al terminar. No son las tablas definitivas de clientes o consumos.

La opción `S01_PSQL` permite usar un cliente PostgreSQL local para estas pruebas. Esa fue la alternativa usada en esta sesión; no sustituye validar Docker.

## 6. `config/`: opciones del proceso

### `config/pipeline.yaml`

Describe opciones como el origen local de los archivos, tamaño de grupos de procesamiento y ruta de las credenciales de `ingesta`.

**Configurar un comportamiento no significa que ya esté implementado.** El proceso de carga sigue pendiente. Este archivo ya no contiene los secretos del scaffolding heredado.

## 7. `data/`: las entradas originales de Bia

No debemos modificar estos archivos, aunque tengan errores intencionales.

- `maestros/clientes.csv`: clientes y datos personales. No copiar filas reales a documentación o logs.
- `maestros/fronteras.csv`: puntos de medición y su relación con clientes.
- `maestros/limites_frontera.csv`: límites operativos por frontera.
- `consumos/`: lecturas horarias de enero a abril y un archivo de correcciones. Los formatos varían.
- `facturacion/`: facturas mensuales en JSON, con información organizada en varios niveles.
- `eventos/mediciones_stream.ndjson`: mediciones para reproducir como mensajes. NDJSON significa que cada línea contiene un objeto JSON independiente.

El pipeline deberá entender y validar esos datos; no arreglaremos los originales manualmente.

## 8. `specs/`: lo que acordamos construir

Un **spec** es una especificación: explica una funcionalidad y cómo comprobaremos que funciona antes de implementarla.

- `README.md`: índice de fases y dependencias.
- `TRACEABILITY.md`: relaciona requisitos de Bia, especificaciones y pruebas. Los códigos `T01`, `T02`, etc. identifican comprobaciones; no todos tienen pruebas implementadas todavía.
- `AMBIGUITIES.md`: dudas del enunciado, ejemplos y recomendaciones pendientes de decisión.
- `S01-contract.md`: preparación del entorno y permisos.
- `S02-privacy.md`: clientes y protección de datos personales.
- `S03-batch.md`: carga de archivos y correcciones. Batch significa procesar datos por lotes.
- `S04-quality.md`: facturación, calidad y archivos de salida.
- `S05-stream.md`: consumo de mensajes y alertas.
- `S06-delivery.md`: descripción de infraestructura y documentación final.
- `S07-validation.md`: validación completa y paquete de entrega.

Solo S01 está autorizado para implementación. Tener S02–S07 escritos no significa que estén construidos.

## 9. `docs/` y `plantillas/`: documentación

`docs/` contiene explicaciones del proyecto:

- `S01.md`: cómo operar S01, qué se comprobó y qué sigue bloqueado.
- `GUIA_DEL_REPOSITORIO.md`: este documento.

`plantillas/` contiene modelos entregados por Bia para completar más adelante:

- `THREAT_MODEL.md`: amenazas de seguridad y controles.
- `SECURITY.md`: protección de datos, permisos y secretos.
- `RUNBOOK.md`: qué hacer si algo falla.
- `DECISIONS.md`: formato para registrar decisiones arquitectónicas. El documento de trabajo está en la raíz.
- `AI_USAGE.md`: cómo usamos IA, qué revisamos y qué errores reales corregimos.

Una plantilla es una estructura para rellenar, no evidencia de un control implementado.

## 10. Carpetas generadas y archivos sensibles

Estas carpetas pueden existir aunque no aparezcan en el mapa inicial:

- `.venv/`: Python y librerías aislados para este proyecto. No es nuestro código y no se incluye en el ZIP.
- `.audit-venv/`: entorno separado que se preparó para intentar instalar el auditor de dependencias. El intento falló; su existencia no significa que se auditó correctamente.
- `__pycache__/`: archivos que Python genera para acelerar la carga de programas.
- `.local/`: configuración privada y recursos de pruebas locales. No se versiona ni se incluye en el ZIP.

Dentro de `.local/`:

- `evaluation.json`: credenciales administrativas y de los roles de evaluación.
- `ingesta.json`: conexión de la cuenta operativa, sin contraseñas de otros roles.
- `postgres_password`: contraseña que Compose entrega a PostgreSQL mediante un archivo secreto.
- `compose.env`: opciones de Compose, como el puerto.
- `pg-test/` y `pg-test.log`: base aislada y archivo de registro usados en las pruebas locales de esta sesión; no son los originales de Bia ni el almacenamiento de Docker.

No copies el contenido de los archivos de credenciales al chat o a capturas. **Todavía no existe una llave PII**: su preparación corresponde a S02. PII significa información que identifica a una persona.

## 11. Partes que todavía faltan

No existe aún `src/`, donde organizaremos el código del pipeline. Tampoco existen `infra/`, `data_classification.yaml` ni los documentos finales de seguridad y operación en la raíz.

`out/` contendrá resultados, como consumo mensual y alertas; `logs/` contendrá eventos del proceso. Sus salidas todavía no las genera un pipeline implementado.

## 12. Cómo se conectan las piezas

La preparación actual sigue este recorrido:

```text
make setup → tools/manage.py → .venv/ + .local/ + entrega.yaml
make up    → tools/manage.py → Docker Compose → PostgreSQL + Redpanda
                            → sql/001_access.sql → permisos y auditoría
make test  → tests/ → comprobaciones de configuración y permisos
```

El procesamiento futuro será:

```text
data/ → pipeline Python → PostgreSQL → resultados en out/
eventos → tools/producer.py → Redpanda → consumidor → alertas
```

Para orientarte, lee primero esta guía; después `README.md` para los requisitos, `specs/S01-contract.md` para el acuerdo y `docs/S01.md` para la evidencia de lo que realmente se probó.
