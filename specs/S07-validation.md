# S07 — Validación final y preparación de entrega

Estado: implementación autorizada; cierre final pendiente de candidato y nueva autorización. No se creó ZIP definitivo ni se ejecutó make down.

Evidencia de esta ejecución: 47 pruebas aprobadas, ninguna fallida/omitida, en 93,748 s. Incluye las 43 anteriores, una regresión setup y tres pruebas de ZIP temporal. La integración real consumió 3.795 eventos y produjo 22/6/5 alertas por tipo. Auditoría previa al empaquetado: 204 archivos seleccionados, 644.780 bytes sin comprimir; revisión sin crear el ZIP del proyecto. Estas cifras de tamaño pueden cambiar al completar candidato/documentos.

## 1. Objetivo
Preparar un manifiesto coherente y empaquetado seguro, verificando sin alterar datos, llaves, servicios o historial.

## 2. Qué vamos a construir
- Corregir prepare para conservar candidato, objetos y credenciales; eliminar solo declaraciones obsoletas conocidas y respetar faltantes concretos.
- Empaquetador con biblioteca estándar, rutas permitidas y exclusiones recursivas. Incluir entrega.yaml y Git completo/autocontenido; out vacío. Sin seguir enlaces ni sobrescribir paquetes.
- Revisar todos los objetos Git, incluso no referenciados, por patrones/credenciales locales conocidas y rutas privadas históricas. Un hallazgo bloquea el paquete; nunca reescribir historia automáticamente.
- Simplificar trazabilidad T01–T34 y actualizar únicamente estados/documentación incorrectos.

## 3. Cómo sabemos que funciona
- **T33:** setup no restaura estado obsoleto; conserva candidato, objetos, configuración y secretos. Pruebas con directorios temporales y simulación de instalación, sin instalar dependencias.
- **T02/T34:** pruebas de ZIP temporal extraído correctamente, CRC, mismas referencias Git y fsck; sin datos, entornos, llaves, estados/cachés ni hooks/logs Git. Bloquear rutas externas, enlaces, sobrescrituras y secretos presentes en blobs sin referencia.
- **T01–T03/T18/T19:** reutilizar suites de privacidad, permisos y entradas hostiles. Revisar nuevamente los eliminatorios en el paquete definitivo, no inferir seguridad absoluta de un escaneo de patrones.
- **T05/T31/T32 final, pendiente:** setup → up → run → run → stream (dos veces para comparar) → test → verificar. Exit 0, batch ≤900 s, streaming ≤300 s; comparar negocio/CSV/DQ/alertas permitiendo cambios operativos de logs/auditoría/métricas. Down solo cuando se autorice.
- **T28:** validate confirmado por el responsable con Terraform 1.17.1; registrar fmt/validate del cierre sin plan/apply.
- **T34 final, pendiente:** apellido_nombre.zip y raíz igual; objetivo <10 MB, manifiesto con candidato completo, fuentes/documentos e historial. El empaquetador no interpreta semánticamente YAML: requiere make verificar y revisión previa. Revisar extracción del paquete definitivo antes de entregarlo.

## 4. Qué no haremos todavía
No crear ZIP definitivo, ejecutar make down, hacer commits/push o cambiar funcionalidades S01–S06. No regenerar ni sobrescribir la llave. No borrar volúmenes ni limpiar datos existentes. Solo ZIP y bases temporales propios de pruebas.

No declarar una prueba desde cero si se ejecuta contra volúmenes existentes. No incluir video en el ZIP salvo instrucción externa; README no fija duración/formato de video.

## 5. Decisiones pendientes
Datos del candidato y horas reales, nombre del paquete y aprobación del cierre. La validación final debe registrar sus resultados reales. Para una ejecución realmente limpia se necesita entorno separado autorizado, sin borrar la instalación actual.

## 6. Referencias técnicas
README §§5–9 y contrato operativo; S01–S06. T01–T03/T05/T18/T19/T28–T34. Plantillas originales conservadas. TRACEABILITY.md contiene el estado consolidado.

## 7. Archivos y responsabilidades

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `tools/package_delivery.py` | Revisión de fuentes/Git y ZIP exclusivo, sin modificar el proyecto. |
| Crear | `tests/test_delivery.py` | Tres pruebas: extracción/Git/exclusiones; límites; secretos en fuentes/historial. |
| Modificar | `tools/manage.py` | Corregir únicamente generación del manifiesto. |
| Modificar | `tests/test_setup.py` | Regresión del recorrido setup/prepare sin rotación. |
| Modificar | `entrega.yaml` | Retirar declaración obsoleta; candidato queda a cargo del responsable. |
| Modificar | `.gitignore` | Excluir dist y ZIP con credenciales de evaluación. |
| Modificar | `README.md` | Estado actual y uso del empaquetador tras autorización. |
| Modificar | `specs/S07-validation.md` | Alcance y pendientes reales. |
| Modificar | `specs/TRACEABILITY.md` | Matriz compacta de todos los criterios. |
| Modificar | `specs/S06-delivery.md`, `DECISIONS.md` | Actualizar evidencia Terraform ya confirmada. |
| Modificar | `RUNBOOK.md`, `SECURITY.md` | Retirar advertencias obsoletas del generador y precisar límites de revisión. |

**Restricciones:** no modificar productor, verificador original, Makefile, Compose, pipeline, SQL, datos, credenciales ni Terraform funcional. No crear nuevos documentos. Un defecto crítico fuera del plan exige diagnóstico y autorización adicional.
