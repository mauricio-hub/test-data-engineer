# S06 — Terraform y documentación técnica

Estado: implementada sin cambiar S01–S05. El responsable confirmó validate satisfactorio en Windows con Terraform 1.17.1; lockfile generado y versionado. Sin despliegue AWS. La evidencia del cierre final se registra en S07.

## 1. Objetivo
Entregar la descripción mínima AWS y documentación defendible de lo construido, sin inventar capacidades ni exposición de datos.

## 2. Qué vamos a construir
- Un archivo Terraform con bucket privado/versionado, bloqueo público, ownership sin ACL, SSE-KMS, TLS y tres roles IAM.
- Separar protected/ (artefactos previamente cifrados), analytics/ (resultados sin PII) y audit/ (registros técnicos). Ingesta lee protected/ y escribe los tres; analista/auditor solo leen su prefijo.
- Confianza STS en tres ARNs explícitos distintos; administración de KMS separada. Decrypt/GenerateDataKey limitados por acción, servicio S3 y contexto de prefijo. No incluir cuentas reales, usuarios IAM ni llaves de acceso.
- Cuatro documentos nuevos, actualizar ADRs y añadir instrucciones al README sin cambiar el enunciado.

## 3. Cómo sabemos que funciona
- **T28:** fmt -check, init -backend=false -input=false y validate satisfactorios cuando exista Terraform. Sin plan/apply, datasources AWS, cargas de objetos ni recursos desplegados. Revisar manualmente confianza, acciones, recursos y contexto KMS; validate no demuestra permisos efectivos AWS.
- **T21:** threat model con al menos ocho amenazas concretas, STRIDE, probabilidad/impacto, control, estado, riesgo residual y mapeo Anexo A 2022. Sin afirmar certificación o mitigaciones inexistentes.
- **T30:** SECURITY referencia política/cifrado/grants/pruebas; DECISIONS contiene al menos cinco ADRs; AI_USAGE usa prompts y errores reales; RUNBOOK explica operación y recuperación sin acciones destructivas.
- **T34 parcial:** README original conservado con instrucciones añadidas; enlaces locales y nombres de funciones/pruebas comprobados. Sin secretos/PII/datos originales en archivos nuevos.
- Hashes de archivos protegidos, originales, manifiesto y generador iguales antes/después. Git ignora data/, llaves, estados y cachés; permite el lockfile real.

## 4. Qué no haremos todavía
Sin integración S3, despliegue AWS, RDS/MSK/cómputo, nuevas dependencias Python, cambios funcionales, commits o ejecución de fases previas. No modificar entrega.yaml ni tools/manage.py: pendientes de S07. No editar specs S01–S05; actualizar estado consolidado en ADRs/trazabilidad.

S3 versionado no es WORM; Terraform no implementa la auditoría SQL. La llave KMS no sustituye Fernet. Esquema pensado para objetos pequeños mediante PutObject, no multipart. El estado Terraform y sus variables locales no se versionan.

## 5. Decisiones pendientes
Registrar fmt y la validación final sin volver a declarar ausente Terraform en Windows. Confirmar entradas reales/trust principals solo si la propuesta se reutiliza fuera de la evaluación; no es necesario suministrarlas para validate. No hay aprobación para desplegar. S07 resolverá manifiesto/generador, validación final, video y empaquetado.

## 6. Referencias técnicas
README §4 C8/E/F, §6, §8 y §9; plantillas originales sin modificar. T21/T28/T30/T34. Evidencia S01–S05: responsable confirmó 43 pruebas y replay 3.795/33 reproducible en Windows; S06 no lo presenta como una nueva ejecución.

## 7. Archivos y responsabilidades

| Acción | Ruta exacta | Responsabilidad |
|---|---|---|
| Crear | `infra/main.tf` | Propuesta S3/KMS/IAM, variables y restricciones de proveedor. |
| Generado y versionado | `infra/.terraform.lock.hcl` | Versiones/hashes reales resueltos por init. |
| Crear | `SECURITY.md` | Controles reales y cómo verificarlos. |
| Crear | `THREAT_MODEL.md` | Flujo, diez amenazas y riesgos residuales. |
| Crear | `AI_USAGE.md` | Herramientas, prompts, revisión y error real. |
| Crear | `RUNBOOK.md` | Comandos operativos y recuperación segura. |
| Modificar | `DECISIONS.md` | Estados actuales y ADRs 009/010 de red/API e IaC. |
| Modificar | `README.md` | Añadir instrucciones sin alterar el enunciado original. |
| Modificar | `.gitignore` | Excluir artefactos privados/cachés/estado; permitir lockfile. |
| Modificar | `specs/S06-delivery.md` | Alcance aprobado, límites y pendientes reales. |
| Modificar | `specs/TRACEABILITY.md` | Evidencia de revisión y validate confirmado por el responsable. |

**Relación:** documentación referencia funciones/SQL/tests existentes; Terraform describe una posibilidad limitada, sin conexión cloud de la aplicación.

**Pruebas y restricciones:** revisión documental y estática sin nuevas suites Python; preservar datos, configuración funcional, puertos, llaves y credenciales. No ejecutar objetivos Make durante esta fase. No afirmar revisión de vulnerabilidades o permisos AWS en vivo sin evidencia.
