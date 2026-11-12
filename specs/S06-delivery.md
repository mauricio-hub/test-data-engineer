# S06 — Infraestructura descrita y documentación

Estado: propuesto. Fase 6 no autorizada. Depende de la arquitectura implementada y de evidencias reales.

## 1. Objetivo
Explicar cómo funciona y se protege la solución, y describir su posible ejecución en AWS sin desplegar recursos.

## 2. Qué vamos a construir
- Terraform para S3, KMS y roles IAM: almacenamiento, gestión de llaves y permisos de AWS.
- Documentos de amenazas, seguridad, decisiones, operación y uso real de IA.
- Instrucciones de ejecución y un manifiesto que refleje lo construido.

## 3. Cómo sabemos que funciona
- **T28:** Terraform describe un bucket S3 cifrado y versionado, una llave KMS con política y roles IAM de menor privilegio equivalentes en responsabilidades a `ingesta`, `analista` y `auditor`. IAM no reemplaza permisos SQL. Se revisan acciones, recursos y acceso público. `terraform validate` pasa tras inicializar sin backend, es decir, sin almacenamiento remoto del estado.
- **T21:** `THREAT_MODEL.md` incluye al menos ocho amenazas concretas mediante STRIDE, categorías para analizar amenazas de seguridad. Describe fronteras de confianza, controles, estado real y correspondencia verificada con el Anexo A de ISO/IEC 27001:2022; no inventa identificadores.
- **T30:** `DECISIONS.md` contiene al menos cinco ADRs, registros de decisiones arquitectónicas, con alternativas, razones y consecuencias. Distingue aprobación de implementación y pendientes.
- **T30:** `SECURITY.md` explica clasificación, cifrado, llaves, permisos, secretos y dependencias con evidencia.
- **T30:** `RUNBOOK.md` cubre fallos parciales, correcciones, rechazos y sospecha de acceso indebido, sin inventar contactos.
- **T30:** `AI_USAGE.md` registra herramientas, dos o tres prompts reales, cambios humanos y un error real con archivo/línea si ocurrió. Si falta evidencia, lo declara; no fabrica una historia.
- **T34:** `README.md` explica requisitos previos, ejecución, alcance y pendientes. `entrega.yaml` coincide con la solución; `no_implementado` declara faltantes.

## 4. Qué no haremos todavía
No ejecutar `terraform plan`, `terraform apply` ni desplegar AWS. No crear repositorio o commits sin autorización. La copia auditada no tenía historial: no afirmar lo contrario ni incorporar datos o secretos al iniciarlo.

## 5. Decisiones pendientes
Verificar que las decisiones documentadas correspondan a la implementación final. Antes de generar la entrega, completar datos del candidato y aprobar cualquier creación de historial.

## 6. Referencias técnicas
- README §4: C8 y Parte F; §6: entrega; §8: uso de IA; §9: comunicación y criterio.
- Plantillas de documentación, incluida la exigencia de cinco ADRs.
- Pruebas: T21, T28, T30 y T34.

## 7. Archivos y responsabilidades

**Archivos que se crearán:** filas «Crear». **Archivos que se modificarán:** filas «Modificar». No se crearán módulos Python ni carpetas vacías en esta fase documental/IaC.

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `infra/main.tf` | Describir Terraform/proveedor, S3, KMS e IAM de la arquitectura; un archivo basta inicialmente. |
| Crear | `THREAT_MODEL.md` | Completar amenazas propias a partir de `plantillas/THREAT_MODEL.md`. |
| Crear | `SECURITY.md` | Explicar controles reales y verificaciones usando `plantillas/SECURITY.md`. |
| Crear | `RUNBOOK.md` | Documentar operación y respuesta a incidentes desde `plantillas/RUNBOOK.md`. |
| Crear | `AI_USAGE.md` | Registrar uso de IA y correcciones reales desde `plantillas/AI_USAGE.md`. |
| Modificar | `DECISIONS.md` | Completar las decisiones ya registradas usando la plantilla como referencia, sin crear otro registro paralelo. |
| Modificar | `README.md` | Incorporar instrucciones y alcance final conservando requisitos y contratos originales de Bia. |
| Modificar | `entrega.yaml` | Completar candidato y faltantes reales, sin cambiar contraseñas o puertos existentes. |
| Modificar | `specs/S06-delivery.md` | Registrar verificaciones editoriales y de Terraform realmente realizadas. |
| Modificar | `specs/TRACEABILITY.md` | Vincular evidencias y pendientes, sin afirmar controles no comprobados. |

**Responsabilidades y relación:** `plantillas/` permanece como material original de referencia; los documentos finales van en la raíz exigida por Bia. Terraform describe el equivalente cloud, sin cambiar el funcionamiento local ni reemplazar permisos SQL con IAM.

**Restricciones:** no desplegar, ejecutar plan/apply, modificar código, Docker, Makefile, puertos, datos o llaves. No crear otro `DECISIONS.md` en `docs/` ni dividir Terraform en archivos solo para imitar una estructura. La edición del manifiesto requiere preservar los objetos generados; cualquier corrección funcional de su generador vuelve al spec correspondiente.

**Pruebas:** no se justifica un archivo Python nuevo para revisar documentación. T28 se verifica con `terraform init -backend=false` y `terraform validate`; T21/T30 mediante revisión de fuentes y contenido; T34 se completa con `tests/test_delivery.py`, propuesto en S07. Registrar herramientas no disponibles como límites, no como pruebas aprobadas.

**Decisiones pendientes adicionales:** políticas exactas de KMS/IAM y requisitos de proveedor antes de escribir Terraform; datos del candidato e historial requieren confirmación humana. Los documentos no pueden afirmar cierre completo de S01/S02 si siguen pendientes sus validaciones normales.

El generador actual reconstruye `objetos` y `no_implementado` al preparar el entorno. Antes de aprobar S06 hay que acordar cómo conservar la declaración final: corregir ese comportamiento mediante el spec propietario o aprobar una ampliación explícita a `tools/manage.py` y `tests/test_setup.py`. Esas dos modificaciones no están autorizadas por la tabla actual; editar únicamente el manifiesto puede no persistir.
