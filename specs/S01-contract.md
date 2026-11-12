# S01 — Preparación del entorno y permisos

Estado: aprobado para implementación, con aclaración humana sobre auditoría y negocio. Implementación realizada; validación completa del entorno pendiente. No autoriza S02.

## 1. Objetivo
Preparar un entorno local reproducible y seguro, con Python, PostgreSQL y Redpanda, que pueda ejecutarse sin pasos manuales.

## 2. Qué vamos a construir
- Preparar dependencias y servicios. Retirar el uso de MinIO si ningún requisito lo justifica.
- Separar la preparación administrativa de la ejecución habitual con el rol `ingesta`.
- Conservar los nombres de los comandos del Makefile.
- Revisar cada dependencia y decidir si conservarla, eliminarla o actualizarla; no elegir versiones sin verificarlas.
- Crear permisos mínimos y un registro de auditoría que permita añadir entradas, pero no modificar las anteriores.

## 3. Cómo sabemos que funciona
- **T02/T20:** no se usa ningún secreto heredado. Existe un inventario de dependencias con decisiones y evidencia de revisión de seguridad.
- **T18:** el propietario de los objetos no puede iniciar sesión. Los roles operativos no son superusuarios, propietarios ni pueden crear roles o bases. `analista` solo lee la vista; `auditor` solo lee auditoría; `ingesta` accede únicamente a lo necesario. Se revocan permisos públicos relevantes y se prueba que no puedan cambiar estructuras ni ampliar sus permisos.
- **T19:** sobre `audit.runs`, los roles operativos no pueden ejecutar `UPDATE`, `DELETE`, `TRUNCATE` ni alterar su estructura. `ingesta` añade registros mediante `audit.record_run`, sin modificar entradas anteriores ni elegir otro actor. Esta prohibición absoluta se aplica a auditoría; en negocio tendrá los permisos específicos necesarios para cargas y correcciones.
- **T33:** `entrega.yaml` coincide con credenciales reales y declara `audit.runs`. El superusuario está disponible para el evaluador y separado de la aplicación. Clientes, consumos y vista analítica siguen como `TODO` hasta sus fases; no crear objetos ficticios para superar `make verificar`.
- **T31:** `make setup` puede repetirse sin interacción; `make up` espera servicios disponibles y prepara la base de forma repetible; `make down` los detiene.
- Los fallos de configuración o conexión devuelven código distinto de cero y mensajes sin secretos. Ningún comando simula éxito sin realizar su trabajo.

## 4. Qué no haremos todavía
No implementar batch ni streaming, desplegar AWS o añadir servicios de orquestación. Tampoco crear tablas de negocio ni la vista definitiva. Sus permisos se prueban ahora con objetos sintéticos aislados; en S02/S03 se concederán explícitamente por objeto, sin permisos globales sobre tablas futuras. El contrato completo se comprobará en S07. `make test` ejecuta las pruebas S01; `make run`, `make stream` y `make clean` fallan explícitamente mientras estén pendientes.

## 5. Decisiones pendientes
Detalles resueltos por delegación del usuario: GNU Make, Python ≥3.11 y Docker Compose v2 con motor Linux; dependencias en `.venv/`; credenciales aleatorias persistentes en `.local/`; manifiesto generado sin llave PII. PostgreSQL recibe su contraseña mediante un archivo secreto de Compose. La futura aplicación recibe solo `.local/ingesta.json`.

A04 sigue pendiente de consulta respecto a la comparación del evaluador; no bloquea crear el registro exigido por C5. No crear historial ni implementar S02. La comprobación completa de conexiones y objetos con `make verificar` queda pendiente de las fases de negocio y los datos del candidato.

## 6. Referencias técnicas
- README §4: C4–C7; §5: contrato de ejecución.
- Archivos: `Makefile`, `entrega.yaml`.
- Pruebas: T02, T18–T20, T31 y T33.
