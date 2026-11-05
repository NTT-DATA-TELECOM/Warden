# Warden

Auditoría **determinista y de solo lectura** de mallas Control-M exportadas en XML. Analiza la malla como un grafo
completo de dependencias (INCOND / OUTCOND / ON-DOCOND / DOFORCEJOB), simula la planificación día a día y detecta jobs
que podrían quedarse sin ejecutar, con su **causa raíz** y su **impacto aguas abajo**.

No se conecta a Control-M ni modifica jobs, folders, calendarios o condiciones.

## Uso

```bash
pip install -r requirements.txt

python -m warden input/complete_workspace.xml --start-date 2026-10-01 --days 365
# o bien
python warden.py "Complete Workspace.xml"
```

| Opción | Descripción |
|---|---|
| `xml ...` | Uno o varios XML (se fusionan en un único workspace) |
| `--start-date` | Primer día lógico simulado (por defecto hoy) |
| `--days` | Días simulados (por defecto 365, configurable) |
| `--config` | Ruta alternativa a `controlm_rules.yaml` |
| `--rules CTM001,CTM004` | Ejecutar solo algunas reglas |
| `--log-level DEBUG\|INFO\|WARNING` | Nivel de log en consola (el fichero en `logs/` siempre es DEBUG) |
| `--output-dir`, `--no-html`, `--no-json` | Salidas |

Salidas: `report/controlm_audit_YYYYMMDD_HHMMSS.html` (filtrable, con subgrafo por hallazgo) y `.json` (estructurado),
y `logs/controlm_audit_YYYYMMDD_HHMMSS.log`.

Tests: `python -m pytest`

## Arquitectura

```
src/warden/
  parser/xml_parser.py        XML -> modelo (sin lógica de auditoría)
  model/                      ControlMWorkspace, ControlMFolder, ControlMJob, Condition, Dependency, Schedule, Finding
  graph/dependency_graph.py   grafo networkx + índices condición->productores/consumidores, job->pred/succ, bloqueo
  scheduler/                  evaluación de calendario (calendar_rules) y simulación con DOFORCEJOB y PREV/NEXT
  rules/                      reglas independientes con identificador + motor + impacto/causa raíz
  report/                     HTML autocontenido y JSON
  config/loader.py            controlm_rules.yaml
  performance/                interfaces para la futura fase de rendimiento (no implementada)
```

Las dependencias se determinan **solo** por coincidencia de nombre de condición entre productor (`OUTCOND +` /
`DOCOND +`) y consumidor (`INCOND`), conservando la ODATE. El formato `A-TO-B` del nombre solo se usa como
comprobación de consistencia (CTM012) y como pista en las recomendaciones.

## Reglas

| Regla | Qué detecta | Severidad |
|---|---|---|
| CTM001 | INCOND que nadie genera, ni externa ni excluida | ALTA (BAJA si hay alternativa OR; MEDIA si es manual, AND/OR ambiguo o el job no se ordena) |
| CTM002 | Dependencia ODAT→ODAT cuyo productor no está planificado en fechas en que el consumidor sí | ALTA (MEDIA si el consumidor solo existe por DOFORCEJOB) |
| CTM003 | La OUTCOND del productor usa PREV/NEXT y genera la condición con otra fecha | ALTA |
| CTM004 | Ciclo de dependencias del mismo día | ALTA si no tiene salida; BAJA si algún miembro tiene un productor alternativo |
| CTM005 | El fallo temporal ocurre en **todas** las fechas en que se ordena el consumidor | ALTA |
| CTM006 | Bloqueo propagado: causa raíz + impacto directo/indirecto | ALTA |
| CTM007 | TIMETO del consumidor anterior al TIMEFROM de todos sus productores | ALTA solo si se configuran las horas de ordenación y MAXWAIT=0; si no, MEDIA |
| CTM008 | OUTCOND sin consumidor | INFO; BAJA si el nombre apunta a un job existente que no la espera |
| CTM009 | Dependencia externa (prefijo/lista) con impacto aguas abajo; CRÍTICA si el impacto ≥ umbral | INFO |
| CTM010 | Condiciones generadas en ON con código distinto de OK | INFO |
| CTM011 | Fan-in alto (umbral configurable) | INFO / MEDIA |
| CTM012 | Nombre `X-TO-Y` incoherente con productor/consumidor reales | MEDIA |
| CTM013 | Borrados sospechosos (`OUTCOND -` de condiciones que esperan otros, +/- contradictorio...) | MEDIA / BAJA / INFO |
| CTM014 | `ON CODE` no reconocido como estado (`NOT OK`, `NOT_OK`...) | MEDIA / BAJA |
| CTM015 | JOBNAME duplicado | INFO |
| CTM016 | Planificación especial (sin criterio, caducado, meses a 0, CONFIRM, folder no ordenado) | INFO |
| CTM017 | Planificación no verificable (UNKNOWN) | INFO |
| CTM018 | Auto-dependencia | ALTA si es el único productor; BAJA si hay otro; INFO si encadena días |
| CTM020 | Dependencia INCOND PREV/NEXT sin productor en la fecha lógica requerida | ALTA |

### Principios

* **No inventar**: toda expresión no soportada da `UNKNOWN` → INFO "No verificable con la información disponible".
  UNKNOWN nunca genera ALTA.
* **Causa raíz**: si un hallazgo ALTA queda dentro del impacto de otro, se subordina a él (`subordinado_a`) y no
  genera otro CTM006.
* El impacto respeta las alternativas: un job solo queda bloqueado si **todas** las alternativas OR de algún grupo
  AND de sus INCOND dependen de jobs bloqueados. En los hallazgos temporales se calcula para la primera fecha
  afectada.

## Simulador

| Elemento | Soporte |
|---|---|
| `DAYS` | `ALL`, `n`, listas, `Ln` (n-ésimo desde el final), exclusiones `-n` / `-Ln` |
| `WEEKDAYS` | `ALL`, `0`..`6` (0 = domingo), listas, exclusiones. `DnWm` y similares → UNKNOWN (se puede configurar `week_start`, aún no se usa) |
| `DAYS_AND_OR` | O / A |
| Meses `JAN`..`DEC` | Sí |
| `DATE` (MMDD) | Sí |
| `ACTIVE_FROM` / `ACTIVE_TILL` | Sí |
| `DAYSCAL` / `WEEKSCAL` / `CONFCAL` | UNKNOWN (las definiciones de calendario no van en el XML) |
| `SHIFT` / `SHIFTNUM` | Solo relevantes con CONFCAL → UNKNOWN; en este XML siempre `Ignore Job` |
| `ODATE` | `ODAT`, `PREV`/`NEXT` (fecha de planificación anterior/siguiente del propio job), `STAT`/`****`/`$$$$` (cualquiera); MMDD explícito |
| `DOFORCEJOB` | Jobs/folders forzados → estado `CONDITIONAL` en las fechas de su forzador |
| Folders sin `FOLDER_ORDER_METHOD` | No se ordenan solos: solo por DOFORCEJOB |
| `TIMEFROM` / `TIMETO` / `MAXWAIT` | En CTM007 |

## Configuración (`config/controlm_rules.yaml`)

* `external_condition_prefixes`, `external_conditions`, `external_condition_patterns`: **dependencias externas**;
  se siguen analizando y se calcula su impacto.
* `excluded_jobs`, `excluded_conditions`, `excluded_folders` + `exclusion_scope`: **exclusiones**; se omiten de las
  reglas indicadas (o de todas).
* `manual_condition_patterns`: condiciones de activación manual (CTM001 baja a MEDIA).
* `simulation.new_day_time`, `simulation.user_daily_times`: horas de ordenación por FOLDER_ORDER_METHOD
  (necesarias para que CTM007 pueda demostrar imposibilidad).
* `thresholds`, `severity_overrides`, `disabled_rules`, `naming`, `valid_on_codes`.

## Resultado sobre el XML real (30-10-2026 08:47, 1.323 jobs, 9 folders)

Ejecución: `--start-date 2026-10-01 --days 365`, **1,4 s**.

**14 ALTA**: 10 causas raíz y 4 CTM006 de bloqueo propagado. Todos revisados a mano contra el XML:

| Causa raíz | Problema | Impacto |
|---|---|---|
| `EXA_DWH_#DwFacDDSP` | Espera `EXAD-CARGA_JOB_FACTURACION`, que nadie genera; es el job que fuerza el folder `DWHRAC_FACTURAC_DDSP_DC2` | 29 jobs |
| `EXA_DWH_#TariDDSPS` | Espera `JOB_KENANFX25_CAP_014_SRVA_FACT_BATCH_P-TO-...` (PREV); el productor no existe en la malla (probable externa no declarada); fuerza `DWHRAC_TARIF_DDSP_DC2` | 23 jobs |
| `EXA_DWH_356_AD-HOC`, `EXA_DWH_276103_CARTERA_DORY` | Esperan `EXAD-EXA_DWH_2521_VANTIVE-TO-...`, pero el job real es `EXA_DWH_2521_UNIFICACION_ODSP`, que genera `...2521_UNIFICACION_ODSP-TO-...` (probable renombrado; el propio 276103 ya borra la condición nueva) | 4 y 2 jobs |
| `EXA_DUM_OK_LAG_CRM_GG` | Espera `EXA_DUM_GOLDENGATE_CRM_B_IGNORE-TO-...`, que nadie genera | 0 |
| `EXA_CALCULA_CAMINO_CRITICO` | Espera `METADATOSCONTROLMJAZZTEL999-TO-...` (sin prefijo externo configurado) | 0 |
| `EXA_DWH_1060_INF_2` (CTM005) | Corre los lunes y espera ODAT de `EXA_DWH_838_AD-HOC`, que solo corre los domingos: **nunca** se satisface | 0 |
| `EXA_DUM_FIN_DEUDORES_MICRO` (CTM002) | Diario; su productor `EXA_DWH_2722_FACT_DEUDORES` solo corre los sábados (313 fechas sin condición) | 0 |
| `EXA_DWH_PURGADO_DESUSER` (CTM002) | Diario; su productor `EXA_DWH_PURGADO_JAZZBI` solo el día 2 (353 fechas) | 0 |
| `EXA_DWH_044_TJAZZTEL_NORMAL` (CTM003) | Corre de domingo a jueves y espera ODAT una condición que `EXA_DWH_054_TJAZZTEL_NORMAL` (L-V) genera con ODATE PREV: los domingos nunca llega (52 fechas) | 0 |

Algunos ALTA con nombres de productor que no existen (`KENANFX25`, `METADATOS...`, `GOLDENGATE..._IGNORE`) pueden
ser dependencias externas legítimas. Si se confirma, basta con añadirlas a `external_conditions` (pasarán a INFO).

Dependencia externa más crítica: `GDW-DWH2JZZ_GEMALTO-TO-EXA_DUM_GEMALTO_JZZ`, de la que cuelgan **174 jobs**.

### Falsos positivos evitados (ajustes con evidencia del XML)

* JOBNAME duplicados → identidad `FOLDER/JOBNAME#JOBISN`.
* Folders sin FOLDER_ORDER_METHOD forzados por DOFORCEJOB → `CONDITIONAL`, no "no planificado".
* `OUTCOND - PREV/NEXT` (limpieza del día anterior) no se marca como borrado sospechoso.
* Arcos PREV/NEXT no forman ciclos; el ciclo `EXA_DWH_1014_CRM ↔ EXA_DWH_1014_CRM_OLD` tiene salida → BAJA.
* Auto-dependencias con productor alternativo → BAJA, no ALTA.
* CTM008 bajó de 166 BAJA a INFO salvo cuando el consumidor que indica el nombre existe en la malla.
* El impacto de CTM001 excluye al propio job causa.

## Qué NO puede verificarse solo con este XML

1. **Horas de ordenación** del New Day (`SYSTEM`) y del User Daily `DWH_18`: sin ellas CTM007 solo puede señalar
   riesgo (MEDIA). Pueden configurarse en `simulation`.
2. **Calendarios** (DAYSCAL/WEEKSCAL/CONFCAL) y semántica de `WEEKDAYS=D6W1` (`EXA_DWH_1550_APOLO` → UNKNOWN).
3. **Condiciones de otros Control-M / sistemas** y su horario de llegada: solo se calcula su impacto.
4. **Jobs sin criterio de planificación** en folders ordenados (pueden ordenarse a mano o desde otra malla).
5. **Resultado real** de los jobs: las condiciones de `ON NOTOK` / `COMPSTAT` / patrones de sysout dependen de la
   ejecución.
6. **Recursos** (`CONTROL`), `CONFIRM`, `MAXRERUN`, ciclos de jobs cíclicos y tiempos de ejecución: no se simulan.
7. Condiciones añadidas manualmente o por scripts (`ctmcontb`) y condiciones que ya existen en el sistema.
8. Si `DOFORCEJOB` ordena realmente con la misma ODATE que el forzador (se asume `ODAT`).
9. Inicio de semana de la instalación y zona horaria (no hay TIMEZONE en el XML).

## Futuras fases

* **Rendimiento** (`performance/`): `JobRun`, `HistoryProvider` y `PerformanceAnalyzer` ya están definidos para
  integrar el histórico (inicio, fin, estado) y calcular camino crítico, P50/P95, cuellos de botella y esperas sobre
  el mismo `DependencyGraph`.
* **IA**: solo para explicar, priorizar o resumir hallazgos a partir del JSON. El motor de validación seguirá siendo
  determinista.
