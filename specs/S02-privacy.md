# S02 — Clientes, clasificación y privacidad

Estado: refactorización aprobada y aplicada dentro del plan. Línea base: 31 pruebas aprobadas; después: las mismas 31 y tres comprobaciones nuevas de compatibilidad aprobadas. Se usaron dependencias fijadas y PostgreSQL real con psql local; el acceso mediante Docker sigue pendiente. No autoriza S03.

## 1. Objetivo
Cargar los clientes sin perder información ni exponer datos personales, incluso cuando contienen texto difícil de interpretar o parecido a SQL.

## 2. Qué vamos a construir
- Leer CSV respetando comillas y campos que ocupan varias líneas.
- Clasificar cada columna del modelo y aplicar esa clasificación antes de guardar o exportar.
- Detectar y enmascarar datos personales en `observaciones`.
- Cifrar en la aplicación los campos restringidos. Usar cifrado autenticado: además de ocultar el contenido, permite detectar alteraciones.
- Relacionar clientes mediante `cliente_id`, sin cruces por NIT.
- Conservar motivo y procedencia de los rechazos, protegiendo su contenido cuando sea necesario.

## 3. Cómo sabemos que funciona
- **T03:** se conservan los 40 clientes o se declara un fallo explícito; nunca se recorta texto silenciosamente. Datos sintéticos con SQL, comillas, texto largo y saltos de línea siguen siendo datos. Procesar clientes no elimina ni cambia consumos.
- **T15:** una columna sin clasificación o con etiqueta inválida bloquea la escritura. Cambiar la clasificación cambia la protección aplicada.
- **T16:** correos, celulares y cédulas sintéticos se enmascaran; varias coincidencias del mismo cliente cuentan una sola vez. Las observaciones no aparecen en la vista analítica ni en `out/`.
- **T17:** incluso el superusuario encuentra únicamente contenido cifrado en campos restringidos, incluidas copias intermedias y cuarentena. Una prueba controlada recupera el original; alterar el contenido cifrado produce un error. La llave no se guarda en PostgreSQL.
- **T01/T26:** errores de lectura, cifrado o SQL no incluyen valores sensibles ni contenido de entrada. Los logs usan JSON y solo campos permitidos.
- **T18:** ninguno de los tres roles accede a llaves o funciones de descifrado. `analista` no lee tablas base ni escribe.
- Si falta la llave o la clasificación es inválida, la operación falla explícitamente; nunca continúa guardando texto claro.

## 4. Qué no haremos todavía
No publicar texto libre ni habilitar descifrado para roles operativos. No implementar todavía el pipeline completo de consumos.

## 5. Decisiones pendientes
A09 resuelta para esta implementación: todos los textos del maestro se clasifican como Restringido-PII por prudencia; `cliente_id` permanece Interno. La vista `analytics.v_clientes` solo expone ese identificador. El mapa efectivo está en `data_classification.yaml`.

Se eligió Fernet de `cryptography`, formato `fernet:v1:` con cliente/columna dentro del contenido autenticado. Correos, celulares colombianos y números de documento se detectan con reglas conservadoras; las observaciones enmascaradas siguen cifradas. Una clasificación incompleta, una degradación sensible o una columna técnica reclasificada sin soporte bloquean la carga.

La llave se conserva fuera del repositorio: setup puede prepararla solo en una instalación nueva comprobada; nunca reemplaza una existente. `BIA_PII_KEY_FILE` conserva prioridad para configuración explícita. Las cargas no generan llaves y demo tiene su propia ubicación predeterminada. Instrucciones y límites de validación: [docs/S02.md](../docs/S02.md).

## 6. Referencias técnicas
- README §4: B7 y C1–C4; §9: criterios eliminatorios.
- Pruebas: T01, T03, T15–T18 y T26.

## 7. Archivos y responsabilidades

**Alcance autorizado:** seguridad, privacidad, clientes y observabilidad. No crear `src/batch/`, `src/quality/` ni validadores ETL en S02. Su creación pertenece a S03, manteniendo la secuencia S03 → S04 → S05.

**Archivos que se crearán:** filas «Crear». **Archivos que se modificarán:** filas «Modificar». La tabla registra el plan concreto aprobado y ejecutado; cualquier ampliación necesita otra autorización.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `src/security/__init__.py` | Definir errores seguros compartidos, sin importar clientes ni coordinadores. |
| Crear | `src/security/encryption.py` | Recibir `Cipher`: llave externa, Fernet y verificación de contexto, sin cambiar formato ni algoritmo. |
| Crear | `src/security/classification.py` | Recibir `Classification` y contratos de columnas; verificar la política y el modelo real. |
| Crear | `src/security/masking.py` | Recibir detección y enmascaramiento PII juntos, con una sola colección de patrones. |
| Crear | `src/client_service.py` | Recibir el flujo existente de clientes: lectura, controles locales, protección, conexión operativa y persistencia. Conservarlo sin añadir ETL general; en S03 delegará las responsabilidades comunes a batch y calidad. |
| Crear | `src/observability.py` | Centralizar eventos JSON permitidos y llamadas de auditoría; recibir valores simples, sin depender de clases del servicio de clientes. |
| Modificar | `src/__init__.py` | Exponer la raíz común del proyecto, sin inicializar servicios. |
| Modificar | `src/privacy.py` | Conservar imports públicos como fachada de seguridad; delegar sin duplicar algoritmos. |
| Modificar | `src/clients.py` | Conservar `python -m src.clients` y funciones públicas como fachada de `src/client_service.py`. |
| Modificar | `tests/test_privacy.py` | Adaptar imports/mocks a sus responsables, conservando todos los casos existentes y comprobando compatibilidad de fachadas. |
| Modificar | `tests/test_privacy_database.py` | Adaptar llamadas sin perder pruebas reales de cifrado, transacciones, cuarentena y permisos. |
| Modificar | `specs/S02-privacy.md` | Registrar aprobación del plan, ejecución y límites reales. |
| Modificar | `specs/TRACEABILITY.md` | Relacionar evidencia nueva con pruebas existentes, sin anticipar resultados. |
| Modificar | `DECISIONS.md` | Registrar separación modular y compatibilidad verificada. |

**Responsabilidades y relación:** `src/clients.py` → `src/client_service.py` → seguridad y observabilidad. `src/privacy.py` → seguridad. Los módulos internos no importan las fachadas. Seguridad no importa el servicio; observabilidad no importa seguridad de clientes ni sus coordinadores. Así se evitan ciclos.

`src/client_service.py` es el único responsable del comportamiento actual de clientes durante S02. Trasladar sus funciones existentes no autoriza crear parsers generales, nuevos validadores o reglas ETL. En S03 se extraerán los componentes comunes y el servicio quedará como coordinación específica de clientes, sin copias de la implementación anterior.

**Restricciones:** conservar las APIs públicas actuales o detallar sus adaptadores mínimos antes de aprobar el plan. Mantener formato `fernet:v1:`, contexto autenticado, enmascaramiento, clasificación, esquema SQL, permisos, resultados y límites transaccionales. No modificar `sql/001_access.sql`, `sql/002_clients.sql`, `data_classification.yaml`, `tools/manage.py`, Makefile, Docker, dependencias, credenciales, puertos o datos. No generar llave PII automáticamente. Si aparece otra ruta necesaria, solicitar ampliación antes de tocarla.

**Pruebas previstas:**
- `tests/test_privacy.py`: T01/T03/T15–T17/T26; lectura multilínea, datos hostiles y largos, clasificación efectiva, enmascaramiento, cifrado/contexto, llave ausente o inválida y errores sin PII. Añadir comprobaciones de los imports públicos de ambas fachadas; no eliminar casos anteriores.
- `tests/test_privacy_database.py`: T03/T15/T17/T18/T26; carga de 40 clientes en base temporal, cifrado visto como superusuario, reejecución estable, cuarentena, permisos y reversión completa ante fallo SQL, sin filtrar PII en logs.
- Repetir sin modificar `tests/test_setup.py` y `tests/test_access.py` como regresión S01.
- Comprobar ausencia de ciclos y que `make clients` mantiene su entrada y falla de forma segura sin llave. Repetir con dependencias fijadas; los resultados previos del entorno alternativo no sustituyen esa prueba.

**Plan aprobado y ejecutado:** línea base antes de editar; extracción de seguridad y observabilidad; traslado del flujo existente a un único servicio; fachadas compatibles; adaptación de pruebas y documentación/type hints. No se cambió SQL, configuración, cifrado, política, dependencias, puertos ni Makefile.

**Evidencia de conservación:** 11 definiciones trasladadas conservan sus cuerpos al comparar el árbol sintáctico, excluyendo docstrings y anotaciones. Se comprobaron parámetros/defaults públicos, descifrado cruzado entre implementación anterior y nueva, y eventos idénticos con reloj fijo. La suite normal conserva el bloqueo previo de Docker en S01; usando `S01_PSQL` local pasa completa: 31 antes y 34 después. No se implementó S03.
