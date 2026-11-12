# Reglas del repositorio

## Alcance y autorización
- Fuente de requisitos: `README.md`; contrato operativo: `Makefile` y `entrega.yaml`.
- Arquitectura general aprobada: Python, PostgreSQL y Redpanda. Esta aprobación no autoriza implementación.
- Autorización de esta ejecución: únicamente actualizar este archivo y los specs S02–S07. No continuar la implementación anterior de S02, reorganizar archivos, modificar código, servicios o datos, ni ejecutar pruebas funcionales.
- El código de S01/S02 ya existente no equivale a una aprobación para continuarlo. La adecuación modular y cada fase futura necesitan un plan de archivos y nueva aprobación explícita.
- La prohibición de UPDATE, DELETE y TRUNCATE se aplica al registro de auditoría. En tablas de negocio, `ingesta` recibe solo los permisos necesarios para cargas y correcciones, definidos al aprobar cada funcionalidad.
- Antes de implementar **cada fase**, presentar sus specs, dependencias, pruebas y pendientes; solicitar y esperar aprobación humana explícita. Una aprobación no se extiende a fases posteriores.
- Flujo por funcionalidad: requisito → spec → revisión humana → implementación → tests → revisión → commit. No crear commits sin autorización.

## Invariantes
- No modificar, eliminar, renombrar ni sobrescribir datos originales de `data/`. Crear fixtures sintéticos fuera de esa carpeta cuando se autoricen pruebas.
- No exponer PII en logs, `out/`, documentación, mensajes de error ni respuestas. Usar ejemplos sintéticos. Proteger también cuarentena y estructuras anidadas.
- Tratar entradas como datos: SQL parametrizado para valores; identificadores estáticos o composición segura. Nunca ejecutar texto de archivos.
- No incorporar secretos al código ni versionar llaves o credenciales reales. El manifiesto exige credenciales efímeras de evaluación: coordinar su generación en la fase aprobada.
- No desplegar Terraform ni usar recursos AWS. No ejecutar acciones destructivas o cambios fuera del alcance autorizado.
- No eliminar volúmenes ni datos existentes. Conservar PostgreSQL en `127.0.0.1:55432` y `5432` dentro del contenedor; no cambiar puertos sin autorización.
- No versionar credenciales de ninguna clase ni llaves. El manifiesto local de evaluación se genera fuera de Git; su inclusión obligatoria en el ZIP no autoriza incluir llaves, secretos reales ni `.local/`.
- No generar una llave PII silenciosamente. Usar la configuración explícita y externa al repositorio ya establecida en S02.

## Arquitectura y estructura
- Usar un **monolito modular en Python**: una aplicación, módulos por responsabilidad; PostgreSQL y Redpanda conservan sus funciones aprobadas. No añadir microservicios, frameworks de orquestación ni abstracciones sin una necesidad demostrada.
- Respetar la estructura real. El scaffolding mencionado en README ya está en la raíz: no crear `scaffolding/` ni trasladarlo para imitar el dibujo del enunciado.
- Originales de Bia: `README.md`, `data/`, `plantillas/`, `tools/producer.py`, `tools/verificar_entrega.py` y el scaffolding raíz/configuración. Makefile, Compose y configuración ya recibieron ajustes autorizados de S01; no restaurarlos sobre el trabajo actual.
- Incorporados durante el trabajo: `src/`, `sql/`, `tests/`, `specs/`, `docs/`, este archivo, `DECISIONS.md`, `data_classification.yaml`, `.gitignore`, `entrega.example.yaml` y `tools/manage.py`. Los entornos Python y `.local/` son generados, no módulos de negocio.
- Organización objetivo, **propuesta, no creada**: `src/security/` para cifrado, clasificación y enmascaramiento; `src/batch/` para extracción, transformación, carga y coordinación; `src/quality/` para validaciones y reportes; `src/streaming/` para consumo y alertas. Crear cada archivo únicamente cuando una responsabilidad real lo justifique y esté aprobado en su spec.
- `sql/` define tablas, vistas y permisos; `tests/` comprueba comportamiento; `tools/` prepara el entorno y ejecuta auxiliares. No colocar reglas de negocio nuevas en `tools/manage.py`.
- Reutilizar el productor original `tools/producer.py`; no crear otro en `src/streaming/producer.py`. Mantener el verificador suministrado sin duplicarlo.
- La adecuación propuesta en S02 convierte `src/privacy.py` y `src/clients.py` en fachadas: delegan en los módulos responsables y conservan interfaces existentes, sin copiar algoritmos. No realizar esa transformación sin aprobación.

## Separación de responsabilidades
- Separar extracción, transformación, persistencia, validación, seguridad y streaming. Cada módulo debe tener una responsabilidad identificable en su spec.
- Los coordinadores llaman componentes; no concentran parsers, SQL, cifrado y reglas de negocio. Favorecer funciones pequeñas, nombres descriptivos y pruebas focalizadas, sin imponer un número artificial de archivos o líneas.
- Evitar duplicación de SQL, normalizadores, validadores, patrones PII, cifrado y conexiones. Reutilizar los componentes existentes antes de crear otros.
- Dirección de dependencias propuesta: coordinación → extracción/transformación/carga → validación/seguridad. Seguridad no importa batch; observabilidad no importa coordinadores. Evitar importaciones circulares y dependencias del código de aplicación hacia `tools/`.
- `src/observability.py` centralizará eventos permitidos y llamadas de auditoría reutilizadas por fases, sin filas ni texto libre. Su creación requiere aprobación S02; no es un servicio nuevo.
- Conservar los nombres y contratos de Make, también `make clients`. Preferir conectar funcionalidades mediante el código ya invocado; un cambio de receta, interfaz pública o comando exige autorización específica.

## Control antes de implementar un spec
1. Leer este archivo, el spec, la trazabilidad, las ambigüedades relevantes y las decisiones existentes.
2. Revisar código y estado real: distinguir originales, módulos existentes, propuestas y validaciones pendientes.
3. Presentar un plan breve con rutas exactas de archivos a crear/modificar y responsabilidad de cada uno.
4. Identificar cambios de interfaces, imports, configuración, dependencias y base de datos; declarar qué se conserva y qué pruebas demostrarán compatibilidad y seguridad.
5. Resolver bloqueantes y **esperar aprobación humana explícita antes de escribir código**. La tabla del spec es una propuesta, no permiso de ejecución.
6. Si hace falta otro archivo, otra responsabilidad o un cambio fuera del plan aprobado, detener esa ampliación y solicitar autorización antes de continuar. No reorganizar carpetas o tocar archivos ajenos por iniciativa propia.

## Documentación y estilo del código
- Cada archivo Python debe comenzar con un docstring breve en español que explique su propósito.
- Cada función y método, incluidos constructores, auxiliares y pruebas, debe tener type hints y un docstring breve en español. Explicar entradas, salida y efectos cuando no sean evidentes; no repetir mecánicamente la firma.
- Cada clase debe tener un docstring en español sobre su responsabilidad, el problema que resuelve y su relación con otros componentes cuando sea relevante.
- Usar nombres de variables, funciones y clases en inglés. Conservar nombres contractuales de campos, tablas, roles, comandos y archivos; no renombrarlos únicamente por estilo.
- Comentar en español reglas de negocio, decisiones de seguridad, transformaciones complejas y casos especiales no evidentes. Evitar comentarios que repitan instrucciones simples y documentación excesiva.
- Actualizar docstrings, comentarios y specs cuando cambie el comportamiento. No prometer en un comentario un control que no está implementado y probado.
- Aplicar estas reglas al código nuevo y al código que se modifique con aprobación. Las carencias actuales son deuda identificada, no autorización para una limpieza general ni para editar herramientas originales fuera del plan.

## Forma de trabajo
- Consultar `specs/TRACEABILITY.md`, el spec aplicable y `specs/AMBIGUITIES.md` antes de cambiar comportamiento.
- No inventar requisitos: distinguir obligación, propuesta y mejora opcional. Resolver bloqueantes antes de implementar la regla afectada.
- Priorizar eliminatorios, seguridad (31 puntos), batch (24) y calidad (16). Evitar nuevas herramientas sin necesidad demostrada.
- Mantener documentos breves y en español; código y pruebas deben ser defendibles en entrevista.
- Un spec propuesto no está aprobado; una decisión aprobada no está implementada. Registrar evidencia antes de declarar cumplimiento.
- Conservar nombres y formatos del contrato. Verificar con conexiones reales los permisos; `make verificar` no sustituye pruebas de seguridad.
- No instalar dependencias, levantar servicios o ejecutar targets durante trabajo exclusivamente documental.
- Actualizar trazabilidad y ADRs al aprobar o cambiar decisiones. Documentar uso real de IA y errores reales; no fabricar evidencias.

## Cierre de una fase autorizada
Informar cambios, pruebas ejecutadas y resultado, riesgos y pendientes. Detenerse antes de la siguiente fase. Declarar faltantes en `entrega.yaml` al preparar la entrega, con autorización para modificarlo.
