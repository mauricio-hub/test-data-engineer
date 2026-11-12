# Ambigüedades y propuestas

Este documento separa lo que exige Bia de las interpretaciones que proponemos. A01–A06 fueron aprobadas internamente al validar S03 y autorizar S04; las decisiones de streaming siguen pendientes. A09 y los detalles operativos de A10 se resolvieron al autorizar S02 y S01, respectivamente. Todos los ejemplos son sintéticos; «Frontera A» representa un punto de medición ficticio.

Las referencias corresponden al [README de Bia](../README.md). Aprobar una interpretación internamente no confirma que coincida con el resultado esperado por el evaluador. En los puntos marcados «Requiere consulta a Bia» recomendamos solicitar esa aclaración antes de implementar; no enviaremos consultas sin autorización. Si no hay respuesta, deberá quedar registrada la interpretación que apruebes y el riesgo asumido.

### A01 — ¿Una corrección inválida reemplaza una lectura válida?

**Origen:** README, §4, Parte B: B3 «Duplicados», B4 «Inválidos» y B5 «Huecos».

**¿Qué pide Bia?**
La mayor `version_lectura` gana; los valores nulos, negativos y superiores a 1.000.000 kWh se descartan y reportan. Una hora sin lectura válida es un hueco. Bia no indica expresamente si debemos elegir la versión antes o después de descartar valores inválidos.

**Ejemplo práctico:**
Para la Frontera A a las 10:00 llegan 100 kWh en versión 1 y −20 kWh en versión 2. Podemos conservar los 100 kWh o dejar esa hora sin lectura válida, según el orden elegido.

**¿Qué debemos decidir?**
Validar primero permite recuperar la versión antigua. Elegir primero la versión reconoce que la corrección reemplaza al dato anterior, aunque después resulte inválida y produzca un hueco. Cambian tanto el consumo mensual como los huecos.

**Recomendación:**
Entre los registros cuya estructura podamos interpretar, seleccionar primero según B3 y después aplicar B4. Si el ganador es inválido, dejar un hueco, sin recuperar una lectura reemplazada. Reportar también las filas inválidas individualmente. Esta es nuestra interpretación, no una regla adicional de Bia.

**Estado:**
Aprobada internamente por el usuario para S03/S04. No consta confirmación de Bia; se conserva el riesgo de interpretación del evaluador.

### A02 — ¿Cómo distinguimos duplicados exactos y conflictivos?

**Origen:** README, §4, Parte B, B3 «Duplicados»; §5, «Archivos de salida — formato exacto», `out/dq_report.json`: ambos contadores cuentan filas sobrantes descartadas, no grupos.

**¿Qué pide Bia?**
Debemos resolver varias lecturas de la misma frontera y hora, y reportar duplicados exactos y conflictivos. Bia define cómo elegir al ganador y qué cantidad contar, pero no qué campos hacen que dos lecturas sean «exactas».

**Ejemplo práctico:**
Para la Frontera A a las 10:00 aparecen dos filas de 100 kWh, versión 1, calidad `OK`, en archivos distintos. Después aparece una de 110 kWh, versión 2. Nuestra propuesta cuenta una fila sobrante exacta y una conflictiva; queda la versión 2.

**¿Qué debemos decidir?**
Comparar el texto original hace distintas dos filas que representan el mismo consumo, por ejemplo 0,1 MWh y 100 kWh. Comparar solo consumo omite diferencias de versión o calidad. Comparar la lectura normalizada permite fijar una definición estable, pero exige acordar qué campos incluye y cómo se relaciona con los rechazos de A01.

**Recomendación:**
Comparar frontera, hora normalizada, kWh, versión y calidad, excluyendo archivo y posición. Recorrer archivos lexicográficamente y sus filas en orden lógico: cada fila sobrante cuenta una vez. Si su firma ya apareció para esa clave, es exacta; si es nueva, conflictiva. B4 se cuenta independientemente, también si coincide con un duplicado.

**Estado:**
Aprobada internamente por el usuario para S03/S04. No consta confirmación de Bia; se conserva el riesgo de interpretación del evaluador.

### A03 — ¿Los reportes describen todos los datos o solo la última ejecución?

**Origen:** README, §4, Parte A, «Datos tardíos»; Parte B, B3 «Duplicados»; Parte E, requisito de `out/metrics.json`; §5, formato de `out/dq_report.json`.

**¿Qué pide Bia?**
Bia exige métricas por ejecución y un reporte de calidad con claves como `filas_leidas` y `correcciones_tardias_aplicadas`. No precisa si cada contador de calidad representa todos los archivos disponibles o únicamente el trabajo nuevo de esa ejecución, ni define por completo qué cuenta como corrección tardía.

**Ejemplo práctico:**
Una primera ejecución lee 100 registros y aplica una corrección de 100 a 110 kWh. Al ejecutar de nuevo sin cambiar archivos, el consumo sigue en 110 kWh. El reporte podría seguir indicando 100 registros y una corrección histórica, o indicar cero cambios nuevos.

**¿Qué debemos decidir?**
Un reporte por ejecución facilita ver el trabajo reciente, pero cambia cuando se omiten archivos ya procesados. Un reporte sobre el conjunto vigente permite comparar calidad entre reejecuciones. También debemos distinguir una corrección por versión de un archivo cuyo nombre simplemente dice «corrección».

**Recomendación:**
Hacer que `dq_report.json` describa el conjunto de entradas vigentes y permanezca estable al reejecutar; usar `metrics.json` para el trabajo de cada ejecución. En el reporte de calidad, `filas_leidas` contará registros lógicos de consumos: una fila CSV completa, aunque ocupe varias líneas físicas. Contar como corrección un incremento de versión que gana sobre una clave frontera-hora ya existente al recorrer los archivos lexicográficamente y sus filas en orden lógico; no deducirla solo del nombre del archivo.

**Estado:**
Aprobada internamente por el usuario para S03/S04. No consta confirmación de Bia; se conserva el riesgo de interpretación del evaluador.

### A04 — ¿Qué debe permanecer idéntico al ejecutar dos veces?

**Origen:** README, §4, Parte A, «Idempotencia»; Parte C, C5 «Trazabilidad»; Parte E, logs y métricas; §5, dos ejecuciones consecutivas de `make run`.

**¿Qué pide Bia?**
Dos ejecuciones deben dejar «exactamente el mismo estado». A la vez, debemos registrar cada ejecución en una bitácora que solo permita añadir registros, con fecha, resultado y conteos. Bia no delimita qué objetos compara al comprobar la igualdad.

**Ejemplo práctico:**
La Frontera A tiene un total mensual de 1.000 kWh. Una segunda ejecución debe mantener ese total y las mismas lecturas. Sin embargo, la bitácora necesita una nueva entrada para demostrar que esa segunda ejecución ocurrió.

**¿Qué debemos decidir?**
Exigir igualdad de toda la base impediría añadir la auditoría requerida. Separar los datos de negocio de la información de ejecución permite cumplir ambos objetivos, pero debemos confirmar que el evaluador aplica esa distinción.

**Recomendación:**
Mantener iguales los datos de negocio, la cuarentena y las salidas que dependen únicamente de esos datos. Añadir una entrada de auditoría por ejecución; permitir que cambien tiempos y contenido operativo de métricas y logs. No actualizar metadatos de una lectura cuando no haya un cambio efectivo.

**Estado:**
Aprobada internamente por el usuario para S03/S04. No consta confirmación de Bia; se conserva el riesgo de interpretación del evaluador.

### A05 — ¿Para qué fronteras y meses contamos horas sin lectura?

**Origen:** README, §4, Parte B, B1 «Zona horaria» y B5 «Huecos»; Parte A, «Descubrimiento de archivos» y tratamiento del archivo corrupto; §5, contadores `horas_sin_lectura_valida_total` y `horas_sin_lectura_valida_por_frontera`.

**¿Qué pide Bia?**
Una hora sin lectura válida es un hueco y no se rellena. El calendario es local de Colombia. No se especifica si debemos revisar todas las fronteras del maestro o solo las observadas, ni si hay que excluir periodos por estado o fecha de registro.

**Ejemplo práctico:**
En abril, la Frontera A tiene 719 horas válidas y la Frontera B no aparece en consumos. Abril tiene 720 horas. Revisar ambas fronteras produciría 721 huecos: uno para A y 720 para B. Revisar solo fronteras observadas produciría uno.

**¿Qué debemos decidir?**
Contar solo lo observado puede ocultar una frontera que no reportó nada. Contar todo el maestro detecta esa ausencia, pero podría incluir fronteras inactivas si Bia esperaba otro criterio. También hay que decidir si un archivo rechazado completo introduce un mes nuevo en el calendario.

**Recomendación:**
Considerar todas las fronteras del maestro y todas las horas de los meses locales identificados en entradas de consumo aceptadas. No filtrar por `estado` o `fecha_registro` sin una regla expresa. Un archivo rechazado completo no añade meses al conjunto que evaluamos.

**Estado:**
Aprobada internamente por el usuario para S03/S04. No consta confirmación de Bia; se conserva el riesgo de interpretación del evaluador.

### A06 — ¿Cómo contamos facturas huérfanas y redondeamos el consumo?

**Origen:** README, §4, Parte B, B6 «Facturación huérfana»; §5, formatos de `out/dq_report.json` y `out/consumo_mensual.csv`.

**¿Qué pide Bia?**
Toda factura con frontera inexistente en el maestro debe ir a cuarentena, sin cargarse al modelo. El reporte incluye `fronteras_huerfanas_facturacion`, cuyo nombre no aclara si cuenta facturas o fronteras distintas. El consumo mensual debe tener tres decimales, pero no se indica el método de redondeo.

**Ejemplo práctico:**
Dos facturas de 50 y 70 kWh apuntan a la misma frontera desconocida: serían dos facturas rechazadas o una frontera huérfana. Por separado, un total mensual de 100,0005 kWh podría publicarse como 100,001 o 100,000 según el método de redondeo.

**¿Qué debemos decidir?**
Contar facturas describe cuántos registros rechazamos; contar fronteras describe cuántos identificadores distintos están afectados. Para los consumos, redondear cada lectura puede alterar el total; redondear al final conserva la precisión de la suma.

**Recomendación:**
Contar facturas rechazadas en `fronteras_huerfanas_facturacion`. Sumar con `Decimal`, aritmética decimal que evita aproximaciones de números binarios, y redondear a tres decimales solo al exportar. Mantener `ROUND_HALF_UP`: en un empate exacto, redondear alejándose de cero; para consumos válidos no negativos, hacia arriba.

**Estado:**
Aprobada internamente por el usuario para S03/S04. No consta confirmación de Bia; se conserva el riesgo de interpretación del evaluador.

### A07 — ¿Cuándo declaramos una ausencia si pueden llegar lecturas tardías?

**Origen:** README, §4, Parte D, reglas `FRONTERA_SIN_REPORTE` y `LECTURA_RETROACTIVA`, y rejilla de 96 intervalos de 15 minutos.

**¿Qué pide Bia?**
Tres intervalos consecutivos sin medición producen una sola alerta por caída, con la hora del tercero. Una medición anterior a la última procesada genera una alerta retroactiva. Bia no define cuánto esperar por datos tardíos, cómo cerrar las ausencias al final del día ni si la alerta de ausencia debe emitirse inmediatamente.

**Ejemplo práctico:**
La Frontera A reporta a las 10:00 y después a las 11:00. Faltan 10:15, 10:30 y 10:45: correspondería una alerta con hora 10:45. Si al final llega una lectura de 5 kWh de las 10:30, ya no hay tres ausencias seguidas en el conjunto final, aunque esa lectura sí llegó tarde.

**¿Qué debemos decidir?**
Alertar mientras llegan eventos exige una política de espera y de tratamiento de alertas ante datos tardíos. Esperar al final de la reproducción permite comprobar la presencia real en toda la rejilla, pero retrasa las alertas y no equivale a detección inmediata en operación continua.

**Recomendación:**
Calcular las ausencias con todas las mediciones de la reproducción acotada, sobre los 96 intervalos. Emitir una alerta en el tercero de cada racha de ausencias, también al final del día. Una medición en la rejilla termina la racha. Detectar retroactividad al llegar cada evento, comparándolo con la mayor hora ya procesada para esa frontera, sin reducir ese máximo ante lecturas tardías. Esta propuesta espera al cierre y no promete alertas inmediatas.

**Estado:**
Requiere consulta a Bia, especialmente sobre emisión inmediata; pendiente también de aprobación humana antes de S05.

### A08 — ¿Qué cantidad de eventos y fecha gobiernan la reproducción?

**Origen:** README, §3, inventario de `mediciones_stream.ndjson` —3.790 eventos—; §4, Parte D, rejilla desde `2026-06-01T00:00:00-05:00`; §5, finalización de `make stream` y ejemplo de `out/alertas.json` fechado en mayo.

**¿Qué pide Bia?**
Debemos consumir el tópico alimentado por el productor suministrado y terminar sin quedar escuchando indefinidamente. La rejilla indicada es junio, pero el ejemplo de salida usa mayo. Además, la inspección del archivo encontró 3.795 eventos, frente a los 3.790 anunciados: ese conteo es una observación nuestra, no un cambio del requisito.

**Ejemplo práctico:**
Una medición de 8 kWh de la Frontera A pertenece al 1 de junio. No debemos moverla a mayo para copiar el ejemplo ni dejar de consumir porque ya llegamos a 3.790 eventos. Una segunda ejecución tampoco debería volver a incorporar la reproducción anterior.

**¿Qué debemos decidir?**
Usar cantidades fijas puede perder eventos o dejar el consumidor esperando. Leer todo el historial del tópico puede mezclar ejecuciones. También debemos elegir entre la fecha normativa de la rejilla y la fecha ilustrativa de la salida.

**Recomendación:**
Procesar todos los eventos reales, sin cantidad fija, y usar la rejilla de junio; interpretar mayo como ejemplo de formato. Capturar las posiciones iniciales y finales por partición de Kafka —los llamados offsets— de cada reproducción y consumir solo ese rango para no mezclar ejecuciones previas.

**Estado:**
Pendiente de aprobación humana antes de S05. La política de ausencias asociada sigue requiriendo consulta a Bia en A07.

### A09 — ¿Qué columnas protegemos y cómo contamos clientes con PII?

**Origen:** README, §4, Parte C, C1 «Clasificación», C2 «PII en texto libre», C3 «Cifrado en reposo» y C4 «Menor privilegio»; §9, primer criterio eliminatorio.

**¿Qué pide Bia?**
Cada columna debe clasificarse como Público, Interno, Confidencial o Restringido-PII, y el pipeline debe usar esa clasificación. Hay que detectar y enmascarar correos, celulares y cédulas en observaciones, reportar clientes afectados y cifrar los campos restringidos. Bia no entrega un mapa de clasificación por columna ni un formato exacto de máscara.

**Ejemplo práctico:**
Un cliente ficticio asociado a una frontera con 100 kWh tiene tres menciones de datos personales en observaciones. El reporte debe representar a un cliente afectado, no tres personas. Aunque se enmascaren las menciones detectadas, el texto podría conservar información sensible no reconocida.

**¿Qué debemos decidir?**
Debemos aprobar la clasificación de todas las columnas y los casos que debe detectar el enmascaramiento. Publicar observaciones ya saneadas da más contexto al analista, pero introduce riesgo residual. Mantenerlas restringidas reduce ese riesgo a costa de limitar el detalle disponible.

**Recomendación:**
Proponer el mapa completo al diseñar el esquema. Clasificar NIT, contactos, dirección y representante como Restringido-PII; mantener restringidas las observaciones incluso después de sanearlas. No incluir texto libre en la vista analítica ni en `out/`. Contar clientes distintos con alguna detección, no el número de coincidencias. El mapa y los casos detectables requieren revisión en S02.

**Estado:**
Resuelta para S02 bajo autorización de implementación: mapa conservador de todos los textos como Restringido-PII, identificador técnico Interno, vista sin texto libre y detección heurística de correos/celulares/documentos. Detalle efectivo en `data_classification.yaml` y `specs/S02-privacy.md`. Esto no constituye una definición adicional atribuida a Bia.

### A10 — ¿Cómo entregamos credenciales locales sin conservar secretos heredados?

**Origen:** README, §3, advertencia sobre seguridad del scaffolding; §4, Parte C, C3 «Cifrado en reposo» —credenciales de superusuario en `entrega.yaml`— y C6 «Secretos»; §5, `make verificar`; §6, manifiesto e historial; §9, segundo criterio eliminatorio.

**¿Qué pide Bia?**
No debe haber credenciales en el código ni seguir vivo el secreto heredado. Al mismo tiempo, el evaluador necesita las credenciales locales del manifiesto para conectarse, incluido el superusuario. Son credenciales de evaluación; esto no autoriza distribuir secretos reales ni la llave que protege la PII.

**Ejemplo práctico:**
El evaluador debe poder entrar a la base y comprobar que una lectura de 100 kWh se relaciona con un cliente cuyos contactos están cifrados. Si el manifiesto y PostgreSQL tienen contraseñas distintas, no puede verificarlo. Si el paquete contiene también la llave de cifrado, se debilita la protección de los datos sensibles.

**¿Qué debemos decidir?**
Omitir las contraseñas impide la evaluación. Reutilizar las del scaffolding mantiene un riesgo eliminatorio. Debemos acordar cómo generar credenciales nuevas, sincronizar el entorno y el manifiesto, custodiar la llave y revisar lo que distribuye el historial.

**Recomendación:**
Generar credenciales efímeras —válidas solo para el entorno local de evaluación— y mantenerlas coherentes entre entorno y manifiesto. No reutilizar credenciales heredadas. Mantener la llave de PII fuera de la base y del paquete. Revisar historial y ZIP para que secretos heredados no queden activos ni se distribuyan inadvertidamente. La revisión no autoriza por sí sola a modificar el historial.

**Estado:**
Resuelta para S01 por delegación técnica del usuario: credenciales aleatorias locales persistidas en `.local/`, manifiesto generado, cuenta de aplicación separada y ninguna llave PII generada. No se autorizó crear o modificar historial. Los datos del candidato y la revisión del paquete siguen pendientes antes de la entrega. Véase [operación S01](../docs/S01.md).

## Otros límites de diseño propuestos

Se mantienen pendientes de aprobación: rechazar completos los archivos estructuralmente corruptos; no convertir unidades desconocidas por suposición; y no rechazar valores de `calidad_lectura` que el README no prohíba. Son decisiones nuestras, dentro del tratamiento de entradas de §4, Partes A y B, no nuevas reglas atribuidas a Bia.

El tratamiento de una fecha u hora malformada, una versión ausente o una frontera desconocida en consumos se detallará como rechazo técnico con evidencia protegida, sin inventar valores para completar el dato.
