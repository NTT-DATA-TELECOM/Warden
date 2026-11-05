# PROYECTO: CONTROL-M MESH AUDITOR

## 1. OBJETIVO

Quiero construir un proyecto en **Python** capaz de auditar automáticamente una malla de **Control-M** exportada en formato XML.

El objetivo principal es detectar errores de diseño, dependencias y planificación que puedan provocar que uno o varios jobs:

- No lleguen a ejecutarse.
- Se queden esperando indefinidamente una condición.
- Esperen una condición que ningún job genera.
- Dependan de un job que no está planificado el mismo día.
- Tengan una dependencia configurada incorrectamente.
- Formen parte de una cadena que queda bloqueada debido a un problema anterior.
- Formen ciclos de dependencias imposibles de resolver.
- Tengan incompatibilidades entre calendario, fecha lógica y dependencias.
- Presenten cualquier otra configuración sospechosa que pueda comprometer la ejecución completa del batch.

El proyecto debe analizar la malla como un **grafo completo de dependencias**, no como jobs aislados.

El resultado debe permitir responder preguntas como:

> ¿Existe algún job que, con esta planificación, pueda quedarse sin ejecutar?

> ¿Hay alguna dependencia que nunca pueda llegar?

> ¿Existe una condición esperada que nadie genera?

> ¿Un error de planificación en JOB_A provoca que JOB_B, JOB_C y otros 40 jobs posteriores tampoco puedan ejecutarse?

> ¿Hay dependencias externas especialmente críticas para el batch?

---

# 2. ENTRADA

El proyecto recibirá uno o varios XML exportados desde Control-M.

Ejemplo de ejecución:

```bash
python controlm_auditor.py "Complete Workspace.xml"
```

El XML proporcionado inicialmente será un **Complete Workspace** de Control-M.

La implementación NO debe estar acoplada exclusivamente al XML de ejemplo. Debe construirse un parser suficientemente modular para soportar futuros XML similares de Control-M.

---

# 3. ELEMENTOS DEL XML A ANALIZAR

Como mínimo deben procesarse:

```text
DEFTABLE
FOLDER
JOB
INCOND
OUTCOND
ON
DOCOND
SHOUT
VARIABLE
```

Y atributos relevantes como:

```text
JOBNAME
JOBISN
APPLICATION
SUB_APPLICATION
PARENT_FOLDER
TASKTYPE
CYCLIC

DAYS
JAN
FEB
MAR
APR
MAY
JUN
JUL
AUG
SEP
OCT
NOV
DEC

TIMEFROM
TIMETO

MAXWAIT
MAXRERUN

SHIFT
SHIFTNUM

RULE_BASED_CALENDAR_RELATIONSHIP

ODATE
AND_OR
SIGN
```

No asumir que todos los atributos aparecen en todos los jobs.

Los valores ausentes deben manejarse correctamente.

---

# 4. MODELO INTERNO

Crear un modelo interno independiente del XML.

Como mínimo:

```text
ControlMWorkspace
ControlMFolder
ControlMJob
Condition
Dependency
Schedule
Finding
```

Un job debe almacenar como mínimo:

```text
job_name
job_isn
folder
application
sub_application
task_type

days
months

time_from
time_to

in_conditions
out_conditions
conditional_actions

max_wait
shift
shift_num
```

El parser XML solamente debe encargarse de convertir el XML en este modelo.

La lógica de auditoría NO debe estar mezclada con el parser XML.

---

# 5. GRAFO DE DEPENDENCIAS

Construir un grafo dirigido de la malla.

Preferentemente utilizar:

```text
networkx
```

si aporta valor.

Representación conceptual:

```text
JOB_A
  |
  | COND_A_B
  v
JOB_B
  |
  | COND_B_C
  v
JOB_C
  +----> JOB_D
  |
  +----> JOB_E
```

Debe poder determinarse:

- Productores de una condición.
- Consumidores.
- Predecesores de un job.
- Sucesores.
- Dependencias directas.
- Dependencias indirectas.
- Caminos.
- Ciclos.
- Jobs aislados.
- Impacto aguas abajo.

IMPORTANTE:

No inferir una dependencia exclusivamente porque el nombre tenga formato:

```text
JOB_A-TO-JOB_B
```

La dependencia debe determinarse utilizando realmente:

```text
OUTCOND
INCOND
ODATE
SIGN
ON/DOCOND
```

El texto del nombre puede utilizarse como comprobación adicional de consistencia, nunca como fuente única de verdad.

---

# 6. CONDICIONES EXTERNAS

Existen condiciones generadas por otros Control-M u otros sistemas.

Actualmente conocemos estos prefijos:

```text
GDW-
1PJ1-
GBI-
```

Una `INCOND` que empiece por uno de estos prefijos y no tenga productor dentro del XML:

**NO ES UN ERROR.**

Debe clasificarse como:

```text
TIPO: DEPENDENCIA EXTERNA
SEVERIDAD: INFO
ESTADO: NO VERIFICABLE DESDE ESTA MALLA
```

Pero NO debe ignorarse.

Debe formar parte del grafo porque puede ser crítica.

Ejemplo:

```text
Control-M externo
       |
       | GDW-COND_X
       v
-------------------------
       |
     JOB_A
       |
     JOB_B
       |
   +---+---+
   |       |
 JOB_C   JOB_D
```

El informe debería poder indicar:

```text
DEPENDENCIA EXTERNA CRÍTICA

GDW-COND_X

Si esta condición no llega:

Jobs directamente afectados: 1
Jobs indirectamente afectados: 37
Total potencialmente bloqueados: 38
```

---

# 7. CONFIGURACIÓN DE REGLAS

NO hardcodear estos prefijos dentro del código Python.

Crear:

```text
config/
    controlm_rules.yaml
```

Ejemplo:

```yaml
external_condition_prefixes:
  - "GDW-"
  - "1PJ1-"
  - "GBI-"

external_conditions: []

excluded_jobs: []

excluded_conditions: []

excluded_folders: []
```

El usuario debe poder añadir nuevos prefijos sin modificar Python.

Diferenciar conceptualmente:

```text
DEPENDENCIA EXTERNA
```

de:

```text
EXCLUSIÓN
```

Una dependencia externa debe seguir siendo analizada.

Una exclusión explícita puede omitirse de determinadas reglas según configuración.

---

# 8. MOTOR DE AUDITORÍA

Implementar reglas independientes.

Cada regla debe tener un identificador.

Como mínimo:

## CTM001 — INCOND sin productor

Un job espera una condición que:

- No genera ningún job de la malla.
- No está declarada como externa.
- No está excluida.

Severidad:

```text
ALTA
```

---

## CTM002 — Productor no planificado

Existe productor, pero en determinadas fechas el consumidor está planificado y el productor no.

```text
ALTA
```

---

## CTM003 — Incompatibilidad ODATE

Detectar incompatibilidades entre:

```text
ODAT
PREV
NEXT
```

y otros valores soportados por Control-M presentes en el XML.

No simplificar `ODATE`.

Debe formar parte de la identidad temporal de una dependencia.

---

## CTM004 — Ciclo

Ejemplo:

```text
A -> B -> C -> A
```

Severidad:

```text
ALTA
```

Mostrar todos los jobs implicados.

---

## CTM005 — Job imposible de ejecutar

Si debido a sus dependencias y planificación puede demostrarse que un job nunca puede satisfacer sus condiciones:

```text
ALTA
```

---

## CTM006 — Bloqueo propagado

Si:

```text
A
|
B
|
C
+--> D
+--> E
```

y A/B tienen un problema que impide la ejecución, calcular todos los jobs afectados aguas abajo.

No generar cientos de alertas independientes sin contexto.

Identificar:

```text
CAUSA RAÍZ
```

y:

```text
IMPACTO
```

---

## CTM007 — Ventana temporal incompatible

Analizar:

```text
TIMEFROM
TIMETO
```

junto con dependencias.

Si puede demostrarse que la planificación hace imposible la ejecución:

```text
ALTA
```

Si únicamente existe riesgo:

```text
MEDIA
```

---

## CTM008 — OUTCOND sin consumidor

Una condición se genera pero ningún job de la malla la consume.

No asumir que es error.

Puede ser externa.

Clasificación inicial:

```text
BAJA / INFO
```

---

## CTM009 — Dependencia externa

Condición con prefijo configurado como externo.

```text
INFO
```

Calcular impacto aguas abajo.

---

## CTM010 — Condiciones generadas en NOTOK

Analizar:

```xml
<ON CODE="NOTOK">
    <DOCOND .../>
</ON>
```

Estas condiciones NO deben tratarse igual que un OUTCOND normal.

Registrar que su generación depende del resultado del job.

---

## CTM011 — Job con elevado fan-in

Detectar jobs con muchas dependencias de entrada.

No considerarlo error.

Clasificar como:

```text
MEDIA / INFO
```

según umbral configurable.

Son puntos especialmente sensibles de la malla.

---

## CTM012 — Nomenclatura sospechosa

Si el nombre:

```text
AAA-TO-BBB
```

parece indicar una dependencia distinta de la que realmente resulta de productores/consumidores:

```text
MEDIA
```

No asumir automáticamente que sea error.

---

## CTM013 — Condición eliminada sospechosamente

Analizar:

```text
OUTCOND SIGN="-"
```

y detectar situaciones potencialmente incorrectas.

---

## CTM020 — Incompatibilidad temporal

Un consumidor está planificado en una fecha determinada pero ninguno de los productores capaces de generar la condición requerida está planificado en la fecha lógica correspondiente.

```text
ALTA
```

Mostrar fechas concretas donde ocurre.

---

# 9. SIMULADOR TEMPORAL

Crear un módulo independiente:

```text
scheduler/
```

que simule la planificación.

Ejemplo:

```bash
python controlm_auditor.py malla.xml \
    --start-date 2026-10-01 \
    --days 365
```

Por defecto:

```text
365 días
```

Debe evaluar, cuando la información disponible lo permita:

```text
DAYS
meses
TIMEFROM
TIMETO
ODATE
PREV
NEXT
SHIFT
SHIFTNUM
MAXWAIT
```

Soportar como mínimo:

```text
DAYS="ALL"
```

días concretos:

```text
3
4
4,14
```

y expresiones que aparezcan realmente en el XML proporcionado.

Por ejemplo:

```text
L1
```

debe analizarse según la semántica de Control-M que corresponda.

---

# 10. REGLA FUNDAMENTAL: NO INVENTAR

Esta regla es obligatoria.

Si la información del XML NO permite determinar con certeza si un job está planificado:

```text
UNKNOWN
```

NO:

```text
FALSE
```

Ejemplo:

```text
PLANNED = TRUE
PLANNED = FALSE
PLANNED = UNKNOWN
```

`UNKNOWN` jamás debe transformarse automáticamente en una alerta ALTA.

Debe aparecer como:

```text
INFO
No verificable con la información disponible.
```

Prefiero perder una alerta antes que generar cientos de falsos positivos.

---

# 11. PROPAGACIÓN DE IMPACTO

Para cada problema ALTA debe calcularse:

```text
job causa
jobs afectados directamente
jobs afectados indirectamente
total
```

Ejemplo de informe:

```text
ALTA — CTM001

JOB:
EXA_DWH_XXXX

PROBLEMA:
Espera COND_X.

No existe ningún productor local y COND_X
no está declarada como dependencia externa.

IMPACTO DIRECTO:
3 jobs

IMPACTO INDIRECTO:
27 jobs

TOTAL:
30 jobs potencialmente bloqueados.
```

---

# 12. CAUSA RAÍZ

Evitar generar alertas repetidas derivadas del mismo problema.

Si:

```text
JOB_A
  X dependencia imposible
   |
 JOB_B
   |
 JOB_C
   |
 JOB_D
```

preferir:

```text
CAUSA RAÍZ:
JOB_A

IMPACTO:
JOB_B
JOB_C
JOB_D
```

en lugar de cuatro alertas ALTA independientes.

---

# 13. INFORME HTML

Generar automáticamente:

```text
report/
    controlm_audit_YYYYMMDD_HHMMSS.html
```

Diseño moderno, limpio y profesional.

Resumen superior:

```text
CONTROL-M MESH AUDIT

Jobs analizados
Folders
Dependencias
Dependencias externas
Errores ALTA
Avisos MEDIA
Avisos BAJA
INFO
```

Clasificación:

```text
🔴 ALTA
🟠 MEDIA
🟡 BAJA
🔵 INFO
```

El HTML debe permitir filtrar por:

```text
severidad
folder
application
sub_application
job
regla
```

Cada hallazgo debe mostrar:

```text
Regla
Severidad
Job
Folder
Descripción
Condición
Productor
Consumidor
Planificación
Causa raíz
Impacto directo
Impacto indirecto
Recomendación
```

---

# 14. GRAFO VISUAL

Si es viable sin convertir el HTML en un fichero gigantesco, incluir visualización del grafo.

Para problemas ALTA sería especialmente útil mostrar únicamente el subgrafo afectado:

```text
        JOB_A
          X
          |
        JOB_B
       /     \
    JOB_C   JOB_D
               |
             JOB_E
```

Diferenciar visualmente:

```text
causa raíz
job bloqueado
job afectado
dependencia externa
```

No intentar representar necesariamente los miles de jobs simultáneamente.

---

# 15. JSON

Además del HTML generar:

```text
report/controlm_audit_YYYYMMDD_HHMMSS.json
```

Debe contener todos los resultados estructurados para futuras automatizaciones.

---

# 16. LOGGING

Crear:

```text
logs/
```

Utilizar `logging` de Python.

No utilizar `print()` como sistema principal de logging.

Permitir:

```bash
--log-level INFO
--log-level DEBUG
```

---

# 17. ESTRUCTURA PROPUESTA

No es obligatorio seguir exactamente esta estructura si propones una mejor, pero quiero separación clara de responsabilidades.

```text
controlm-mesh-auditor/
│
├── README.md
├── requirements.txt
├── pyproject.toml
│
├── input/
│   └── .gitkeep
│
├── config/
│   └── controlm_rules.yaml
│
├── report/
│   └── .gitkeep
│
├── logs/
│   └── .gitkeep
│
├── src/
│   └── controlm_auditor/
│       │
│       ├── __init__.py
│       ├── cli.py
│       │
│       ├── parser/
│       │   └── xml_parser.py
│       │
│       ├── model/
│       │   ├── job.py
│       │   ├── condition.py
│       │   ├── schedule.py
│       │   └── finding.py
│       │
│       ├── graph/
│       │   └── dependency_graph.py
│       │
│       ├── scheduler/
│       │   └── simulator.py
│       │
│       ├── rules/
│       │   ├── orphan_conditions.py
│       │   ├── cycles.py
│       │   ├── temporal.py
│       │   ├── external.py
│       │   └── impact.py
│       │
│       ├── report/
│       │   ├── html_report.py
│       │   └── json_report.py
│       │
│       └── config/
│           └── loader.py
│
└── tests/
    ├── fixtures/
    ├── test_parser.py
    ├── test_dependencies.py
    ├── test_scheduler.py
    ├── test_external_conditions.py
    ├── test_cycles.py
    └── test_impact.py
```

---

# 18. TESTS

Quiero tests automatizados.

Como mínimo:

### Dependencia correcta

```text
A -> B
```

Debe dar OK.

### Dependencia inexistente

```text
B espera X
```

pero nadie genera X.

Debe producir CTM001.

### Dependencia externa

```text
B espera GDW-X
```

Debe producir INFO, nunca ALTA.

Lo mismo para:

```text
1PJ1-
GBI-
```

### Ciclo

```text
A -> B -> C -> A
```

Debe producir CTM004.

### Propagación

```text
A -> B -> C -> D
```

si A es imposible:

```text
impacto = B,C,D
```

### Calendarios incompatibles

Productor y consumidor con días incompatibles.

Debe detectarse.

### UNKNOWN

Una expresión de calendario no soportada debe producir:

```text
UNKNOWN
```

y nunca convertirse automáticamente en error.

---

# 19. RENDIMIENTO

La malla puede contener miles de jobs y miles de condiciones.

No utilizar algoritmos O(n²) innecesariamente.

Construir índices:

```text
condition -> producers
condition -> consumers
job -> predecessors
job -> successors
```

El análisis de una malla de aproximadamente 1.500 jobs debe tardar segundos, no minutos.

---

# 20. SEGURIDAD

El programa inicialmente será completamente:

```text
READ ONLY
```

No se conectará a Control-M.

No modificará:

```text
jobs
folders
calendarios
condiciones
```

Solo analizará XML.

---

# 21. FUTURA FASE DE RENDIMIENTO

Diseñar la arquitectura pensando en una futura ampliación.

Más adelante proporcionaré información histórica como:

```text
JOB
fecha
hora inicio
hora fin
duración
estado
```

Con esos datos quiero poder calcular:

```text
camino crítico
P50 duración
P95 duración
máximos
cuellos de botella
tiempos de espera entre jobs
paralelismo desaprovechado
jobs que retrasan el fin del batch
```

y responder:

> ¿Qué modificaciones de la malla podrían adelantar la hora de finalización del batch?

NO implementar esta parte todavía salvo las interfaces/modelos que consideres razonables para facilitar la ampliación.

---

# 22. IA

El núcleo de validación NO debe depender de un LLM.

Las decisiones:

```text
existe dependencia
no existe dependencia
hay ciclo
calendarios compatibles
impacto aguas abajo
```

deben ser deterministas en Python.

En el futuro se podría utilizar IA para:

```text
explicar hallazgos
priorizar recomendaciones
proponer cambios
resumir el informe
```

pero nunca para sustituir el motor determinista.

---

# 23. XML INICIAL

Voy a proporcionar junto a este prompt un XML real exportado desde Control-M.

ANTES DE PROGRAMAR:

1. Analiza completamente el XML.
2. Identifica todas las etiquetas utilizadas.
3. Identifica todos los atributos de planificación.
4. Obtén los diferentes valores existentes de `DAYS`.
5. Obtén los diferentes valores existentes de `ODATE`.
6. Identifica `INCOND`, `OUTCOND`, `DOCOND` y acciones `ON`.
7. Identifica configuraciones de calendario que el simulador necesite soportar.
8. Identifica cualquier elemento relevante que este prompt no haya contemplado.
9. Documenta brevemente los hallazgos.
10. Solo entonces comienza la implementación.

NO adaptes el XML a tu diseño.

Adapta el diseño a la realidad encontrada en el XML.

---

# 24. VALIDACIÓN FINAL

Una vez implementado:

1. Ejecuta todos los tests.
2. Ejecuta el auditor contra el XML real proporcionado.
3. Genera HTML.
4. Genera JSON.
5. Revisa los hallazgos.
6. Comprueba especialmente los `ALTA`.
7. Busca falsos positivos.
8. Ajusta las reglas cuando exista evidencia objetiva.
9. Vuelve a ejecutar.
10. Documenta qué cosas no pueden verificarse únicamente con este XML.

No quiero que simplemente termines cuando el código compile.

Quiero una ejecución real contra la malla proporcionada.

---

# 25. PRINCIPIO GENERAL DEL PROYECTO

El objetivo no es producir el mayor número posible de alertas.

El objetivo es producir **pocas alertas, fiables y accionables**.

Ante la duda:

```text
UNKNOWN / INFO
```

es preferible a:

```text
ALTA
```

si no existe evidencia suficiente para demostrar el problema.

La herramienta debe ayudar a encontrar problemas reales de Control-M y no obligar al usuario a revisar cientos de falsos positivos.

---

# RESULTADO ESPERADO

Al finalizar quiero poder ejecutar algo parecido a:

```bash
python -m controlm_auditor \
    input/complete_workspace.xml \
    --start-date 2026-10-01 \
    --days 365
```

y obtener:

```text
report/
├── controlm_audit_20261029_120000.html
└── controlm_audit_20261029_120000.json
```

con una auditoría completa y trazable de la malla.

Empieza analizando el XML proporcionado y, antes de implementar, indícame cualquier característica relevante del XML que obligue a modificar o ampliar este diseño.