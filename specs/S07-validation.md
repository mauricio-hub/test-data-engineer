# S07 — Validación final y paquete de entrega

Estado: propuesto. Fase 7 no autorizada. Depende de S01–S06.

## 1. Objetivo
Comprobar la solución completa como la ejecutará el evaluador y preparar un paquete coherente, sin datos originales ni secretos indebidos.

## 2. Qué vamos a construir
- Una ejecución de verificación completa en un entorno local limpio.
- Evidencia de resultados, tiempos, permisos y criterios eliminatorios.
- El ZIP final con los archivos y estructura exigidos.

## 3. Cómo sabemos que funciona
- **T31:** ejecutar `make setup → make up → make run → make run → make stream → make test → make down`. Cada `make run` tarda como máximo 900 segundos y `make stream`, 300. Limpiar únicamente recursos de prueba autorizados; nunca originales.
- **T05:** comparar datos de negocio y salidas reproducibles entre ejecuciones; justificar diferencias permitidas por A04. Confirmar correcciones y un mes nuevo usando datos sintéticos aislados.
- **T01/T02/T03:** comprobar los tres eliminatorios sobre la solución real y el paquete: exposición de datos personales, persistencia del secreto heredado y ejecución de entradas hostiles. No limitarse a pruebas unitarias.
- **T18/T19/T33:** conectar con `ingesta`, `analista`, `auditor` y superusuario; intentar operaciones prohibidas. Ejecutar `make verificar` con servicios activos y salidas generadas, antes de `make down`. Su éxito no sustituye comprobar que las operaciones prohibidas fallan.
- **T29:** la suite usa casos pequeños con resultados esperados calculados de forma independiente y pruebas de integración. No altera `data/` ni necesita secretos reales.
- **T34:** generar `apellido_nombre.zip`, con raíz `apellido_nombre/` y entregables exigidos. Excluir `data/`, `.venv/`, `node_modules/`, volúmenes y llaves. Revisar historial si existe. Objetivo: menos de 10 MB. Las credenciales del manifiesto son solo efímeras para evaluación local.
- Registrar comandos ejecutados, resultados, duración y limitaciones.

## 4. Qué no haremos todavía
No declarar puntaje ni aprobación del evaluador a partir de pruebas locales. No ampliar el alcance una vez satisfechos los criterios. No modificar originales ni limpiar recursos sin autorización.

## 5. Decisiones pendientes
Confirmar A04 para la comparación entre ejecuciones. Resolver pendientes de S01–S06 y revisar cualquier funcionalidad declarada en `no_implementado` antes de cerrar.

## 6. Referencias técnicas
- README §§5–9: contrato, entrega, reglas, uso de IA y evaluación.
- Pruebas: T01–T03, T05, T18, T19, T29, T31, T33 y T34.

## 7. Archivos y responsabilidades

**Archivos que se crearán:** filas «Crear». **Archivos que se modificarán:** filas «Modificar». La fase verifica y empaqueta; no incorpora funcionalidades pendientes.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `tools/package_delivery.py` | Construir y revisar el ZIP requerido con exclusiones explícitas; sin borrar originales, volúmenes ni paquetes anteriores. |
| Crear | `tests/test_delivery.py` | Probar estructura, exclusiones, límites de rutas y contenido permitido del paquete mediante fixtures sintéticos. |
| Modificar | `.gitignore` | Evitar versionar el archivo de entrega generado y sus credenciales locales incluidas por contrato. |
| Modificar | `README.md` | Registrar comandos de validación, resultado y limitaciones finales sin cambiar el enunciado. |
| Modificar | `entrega.yaml` | Confirmar candidato, objetos y pendientes preservando credenciales y puertos. |
| Modificar | `specs/S07-validation.md` | Registrar aceptación o fallos del recorrido final. |
| Modificar | `specs/TRACEABILITY.md` | Reflejar pruebas ejecutadas y requisitos pendientes. |

**Responsabilidades y relación:** el empaquetador consume archivos ya construidos; no reimplementa pipeline, verificador ni seguridad. Reutilizar `tools/verificar_entrega.py` y las suites existentes S01–S05. Los nombres reales del ZIP y carpeta raíz dependen del candidato; se acordarán antes de generar el archivo.

**Restricciones:** excluir `data/`, `.local/`, `.venv/`, `.audit-venv/`, llaves y volúmenes; incluir `entrega.yaml` con credenciales exclusivamente efímeras de evaluación. No reescribir historial ni crear commits sin autorización. Conservar Makefile y sus comandos. Si falla una función, volver al spec propietario con un plan aprobado; no arreglarla de forma incidental durante esta validación.

**Pruebas:** `tests/test_delivery.py` cubre T34 y exclusión de secretos T02; para T01/T03/T05/T18/T19/T29 reutilizar los archivos de prueba declarados en S02–S05 y `tests/test_setup.py`/`tests/test_access.py`. T31/T33 se verifican con el recorrido Make y el verificador reales en el entorno autorizado. No crear una segunda suite que copie esos casos.

**Decisiones pendientes adicionales:** ruta/nombre del ZIP, datos del candidato y entorno limpio aislado. Ninguna limpieza de recursos existentes está autorizada por esta propuesta; comprobar desde cero con recursos nuevos propios requiere aprobación previa de su preparación.
