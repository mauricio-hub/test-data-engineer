# Specs y fases

Estado: arquitectura general, S01 y S02 autorizados. Permisos y privacidad implementados; validación con Docker/dependencias fijadas pendiente por restricciones del entorno. Ver [S01](../docs/S01.md) y [S02](../docs/S02.md). S03 y fases posteriores siguen sin autorización.

| Fase | Spec | Dependencias | Aceptación de fase |
|---|---|---|---|
| 0 | Este directorio, `AGENTS.md`, `DECISIONS.md` | Ninguna | Revisión humana de documentos y ambigüedades |
| 1 | [S01 Contrato y bootstrap](S01-contract.md) | Aprobación Fase 1; A04, A10 | Arranque reproducible y conexiones verificables |
| 2 | [S02 Protección de clientes](S02-privacy.md) | S01; A09 | Clientes preservados y PII protegida |
| 3 | [S03 Ingesta batch](S03-batch.md) | S02; A01–A03, A05 | Precedencia, reintentos y aislamiento de corrupción |
| 4 | [S04 Calidad y publicación](S04-quality.md) | S03; A02–A06 | Facturación y salidas exactas |
| 5 | [S05 Streaming](S05-stream.md) | S01; A07–A08 | Alertas correctas y cierre acotado |
| 6 | [S06 Terraform y documentación](S06-delivery.md) | Arquitectura final | Validación y documentación fiel |
| 7 | [S07 Validación de entrega](S07-validation.md) | S01–S06 | Contrato limpio y revisión de eliminatorios |

Las pruebas Txx son identificadores de casos futuros, no archivos existentes. Observabilidad y pruebas se incorporan desde la fase correspondiente. Las ambigüedades están en [AMBIGUITIES.md](AMBIGUITIES.md) y la cobertura en [TRACEABILITY.md](TRACEABILITY.md).
