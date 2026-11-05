# Análisis previo del XML (Complete Workspace 30-10-2026 08:47)

Fichero: `input/complete_workspace.xml` (3 MB, exportado de Control-M 9.20, datacenter `ctmjp`).
Scripts de perfilado: `tools/profile_xml.py`, `tools/profile_deps.py` (salidas en `tools/*.txt`).

## 1. Volumetría y etiquetas

| Etiqueta | Nº | Padre |
|---|---|---|
| DEFTABLE | 1 | raíz |
| FOLDER | 9 | DEFTABLE |
| JOB | 1.323 | FOLDER |
| INCOND | 4.638 | JOB |
| OUTCOND | 9.587 (4.978 `+`, 4.609 `-`) | JOB |
| ON | 376 | JOB |
| DOCOND | 348 | ON |
| DOMAIL | 110 | ON |
| DOFORCEJOB | 26 | ON |
| DOACTION | 19 | ON |
| DOSHOUT | 1 | ON |
| SHOUT | 33 | JOB |
| VARIABLE | 458 | JOB |
| CONTROL | 7 | JOB |

No hay `SMART_FOLDER`, `SUB_FOLDER`, `RULE_BASED_CALENDARS`, `QUANTITATIVE`, ni condiciones a nivel de folder.

## 2. Atributos de planificación encontrados

| Atributo | Valores |
|---|---|
| DAYS (1.130 jobs) | `ALL` (1.043), `L1` (36), números sueltos, listas (`4,14`, `1,7,14`, `2..31`), `L1,15`, `L1,14`, `L1,7,14,21` |
| WEEKDAYS (103 jobs) | `0`..`6`, listas (`1,2,3,4,5`, `0,6`...), `ALL`, **`D6W1`** |
| DAYS_AND_OR | `O` (1.314), `A` (9) |
| Meses JAN..DEC | siempre presentes; patrones `111111111111`, `000000000000` (10 jobs), `100100100100` (trimestral, 9) |
| DATE | `0106` (3 jobs, con todos los meses a 0) |
| ACTIVE_FROM / ACTIVE_TILL | 1 y 1 (`ACTIVE_TILL=20150511` → job caducado) |
| SHIFT / SHIFTNUM | siempre `Ignore Job` / `+00` |
| RULE_BASED_CALENDAR_RELATIONSHIP | siempre `O` |
| DAYSCAL / WEEKSCAL / CONFCAL | **no aparecen** |
| TIMEFROM (278) / TIMETO (228) | `HHMM`; TIMETO `>` (205 = sin límite); 2 ventanas que cruzan medianoche (`2345-0020`, `0800-0005`) |
| MAXWAIT | 0 (78), 1 (1.181), 2, 3, 5 |
| CYCLIC | 58 jobs cíclicos (INTERVAL / CYCLIC_TIMES_SEQUENCE / CYCLIC_INTERVAL_SEQUENCE) |
| CONFIRM | 1 job con confirmación manual |
| TASKTYPE | `Job` 1.132, `Dummy` 189, `Command` 2 |

Jobs sin ningún criterio (ni DAYS, ni WEEKDAYS, ni DATE): **100**, de los cuales 53 pertenecen a los folders forzados.

## 3. ODATE y condiciones

| | ODAT | PREV | NEXT |
|---|---|---|---|
| INCOND | 4.543 | 90 | 5 |
| OUTCOND | 9.469 | 100 | 18 |
| DOCOND | 345 | 0 | 3 |

- `INCOND AND_OR`: `A` (4.633) y `O` (5, en 3 jobs; nunca mezclados con `A`).
- No aparecen `STAT`, `****`, `$$$$` ni fechas explícitas, pero el parser los conserva y el simulador los trata (`STAT/****/$$$$` = cualquier fecha; otros = UNKNOWN).
- 32 condiciones esperadas sin productor: 17 `1PJ1-`, 6 `GDW-`, 1 `GBI-` y 8 sin prefijo externo.
- 348 OUTCOND `+` sin consumidor dentro de la malla (113 `GBI-`, 56 `1PJ1-`: salidas hacia otros sistemas).
- 16 condiciones consumidas tienen más de un productor.

## 4. Acciones ON

`ON CODE`: `NOTOK` (285), `OK` (65), `*Codigo de retorno: 66*` (13), `COMPSTAT EQ 0/3/8/ANY`, `NOTSUB`, `*`, `Hay ficheros que procesar`,
y los valores anómalos **`NOT OK`** (2) y **`NOT_OK`** (1), que Control-M no reconoce como estado.

Acciones: `DOCOND` (+/-), `DOFORCEJOB`, `DOACTION` (`OK`, `NOTOK`, `SPCYC`), `DOMAIL`, `DOSHOUT`.

## 5. Hallazgos que obligan a ajustar el diseño

1. **JOBNAME no es único** (`EXA_DWH_851_ODSP_DDSP`, `EXA_DWH_044_TJAZZTEL`, `EXA_CHECK_INVALID_OBJECTS`).
   → Identidad del job = `FOLDER/JOBNAME#JOBISN`.
2. **Folders sin FOLDER_ORDER_METHOD** (`DWHRAC_FACTURAC_DDSP_DC2`, `DWHRAC_TARIF_DDSP_DC2`): no los ordena el New Day ni un User Daily;
   se ordenan con `DOFORCEJOB` desde `EXA_DWH_#DwFacDDSP` (NAME=`*`) y `EXA_DWH_#TariDDSPS` / `EXA_DWH_685_TAR`.
   → Hay que modelar `DOFORCEJOB`. Un job forzado queda planificado como `CONDITIONAL` en las fechas en que se planifica su forzador.
3. **FOLDER_ORDER_METHOD** = `DWH_18` (User Daily) o `SYSTEM` (New Day). Las horas reales de ordenación no están en el XML.
   → Se configuran opcionalmente (`new_day_time`, `user_daily_times`). Sin ellas, la ventana horaria solo genera riesgo (MEDIA), nunca ALTA.
4. **Jobs sin criterio de planificación** en folders ordenados: Control-M no los ordena automáticamente (pueden lanzarse a mano o forzarse).
   → Estado `NOT_SCHEDULED`. Solo es ALTA cuando son el único productor de una condición que espera un job planificado.
5. **`WEEKDAYS=D6W1`**: su semántica depende del inicio de semana de la instalación. → `UNKNOWN`, salvo que se configure `week_start`.
6. **`ACTIVE_FROM` / `ACTIVE_TILL`**, `DATE`, meses a 0 y `DAYS_AND_OR=A`: se soportan en el simulador.
7. **Auto-dependencias**: 8 jobs esperan una condición que producen ellos mismos. Solo hay bloqueo si no existe otro productor.
8. **Ciclo real** `EXA_DWH_1014_CRM` ↔ `EXA_DWH_1014_CRM_OLD`, con salida alternativa (`EXA_DWH_2994_CRM_OFFLINE_GG`).
   → CTM004 distingue un ciclo cerrado (ALTA) de un ciclo con salida (BAJA).
9. **PREV/NEXT** se usan a menudo para borrar la condición del día anterior (`OUTCOND - PREV`) y para cadenas entre días.
   → Los arcos que cruzan de día no cuentan para detectar ciclos; PREV/NEXT se resuelven con el calendario del propio job.
10. **Nombres de condición con JOB_ y EXA_ mezclados** (`EXAD-JOB_DWH_763_...-TO-JOB_DWH_800_TARIFA` → `EXA_DWH_800_TARIFA`).
    → CTM012 normaliza prefijos configurables antes de comparar.
11. **Condiciones probablemente renombradas**: `EXA_DWH_276103_CARTERA_DORY` espera `EXAD-EXA_DWH_2521_VANTIVE-TO-...`,
    pero borra `EXAD-EXA_DWH_2521_UNIFICACION_ODSP-TO-...`, que es la que realmente se genera. → CTM001 añade sugerencias de condiciones parecidas.
12. **Condiciones de tipo manual** (`EXAD-CARGA_JOB_FACTURACION`, `...-EJECUCION_MANUAL`) y de otros sistemas sin prefijo configurado
    (`METADATOSCONTROLMJAZZTEL999-`, `JOB_KENANFX25_...`). → El usuario puede declararlas en `external_conditions` / `external_condition_prefixes`.
13. **Códigos ON no estándar** (`NOT OK`, `NOT_OK`). → Nueva regla CTM014.
14. Elementos fuera del alcance del prompt que se registran pero no condicionan la validación: `CONTROL` (recursos exclusivos), `SHOUT`, `DOMAIL`,
    `CONFIRM`, `END_FOLDER`, `VARIABLE`, cíclicos.

## 6. Reglas añadidas por el análisis

| Regla | Descripción | Severidad |
|---|---|---|
| CTM014 | Código ON no reconocido como estado (`NOT OK`, `NOT_OK`) | MEDIA |
| CTM015 | JOBNAME duplicado entre folders | INFO |
| CTM016 | Planificación especial: sin criterio, caducado, meses a 0, confirmación manual, folder no ordenado | INFO |
| CTM017 | Expresión de planificación no verificable (UNKNOWN) | INFO |
| CTM018 | Auto-dependencia con productor alternativo | BAJA |
