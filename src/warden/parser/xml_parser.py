"""Conversión de XML de Control-M al modelo interno.

Este módulo únicamente traduce XML a objetos del modelo; no contiene lógica de auditoría.
Soporta DEFTABLE con FOLDER / SMART_FOLDER / TABLE / SMART_TABLE y SUB_FOLDER anidados.
"""
from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from ..model import (
    MONTH_ATTRS, Condition, ConditionalAction, ConditionRole, ControlMFolder, ControlMJob,
    ControlMWorkspace, ForceJob, Schedule,
)

log = logging.getLogger(__name__)

FOLDER_TAGS = {"FOLDER", "SMART_FOLDER", "TABLE", "SMART_TABLE", "SCHED_TABLE", "SCHED_GROUP"}
SUB_FOLDER_TAGS = {"SUB_FOLDER"}
JOB_TAGS = {"JOB"}
KNOWN_JOB_CHILDREN = {"INCOND", "OUTCOND", "ON", "SHOUT", "VARIABLE", "CONTROL", "QUANTITATIVE", "RULE_BASED_CALENDARS"}
KNOWN_ON_CHILDREN = {"DOCOND", "DOFORCEJOB", "DOACTION", "DOMAIL", "DOSHOUT", "DOAUTOEDIT", "DORULE", "DOSYSOUT", "DOREMEDY", "DOOUTPUT"}


def _int(value: str | None) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except ValueError:
        return None


def _flag(value: str | None) -> bool | None:
    if value is None:
        return None
    return value.strip() in ("1", "Y", "y")


def _local(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _parse_schedule(a: dict[str, str]) -> Schedule:
    return Schedule(
        days=a.get("DAYS") or None,
        weekdays=a.get("WEEKDAYS") or None,
        days_and_or=(a.get("DAYS_AND_OR") or "O").upper(),
        months={i + 1: _flag(a.get(m)) for i, m in enumerate(MONTH_ATTRS)},
        date=a.get("DATE") or None,
        active_from=a.get("ACTIVE_FROM") or None,
        active_till=a.get("ACTIVE_TILL") or None,
        days_cal=a.get("DAYSCAL") or None,
        weeks_cal=a.get("WEEKSCAL") or None,
        conf_cal=a.get("CONFCAL") or None,
        shift=a.get("SHIFT") or None,
        shift_num=a.get("SHIFTNUM") or None,
        rbc_relationship=a.get("RULE_BASED_CALENDAR_RELATIONSHIP") or None,
        time_from=a.get("TIMEFROM") or None,
        time_to=a.get("TIMETO") or None,
        max_wait=_int(a.get("MAXWAIT")),
        max_rerun=_int(a.get("MAXRERUN")),
        cyclic=(a.get("CYCLIC") or "0") == "1",
        interval=a.get("INTERVAL") or None,
        cyclic_type=a.get("CYCLIC_TYPE") or None,
        cyclic_times_sequence=a.get("CYCLIC_TIMES_SEQUENCE") or None,
        cyclic_interval_sequence=a.get("CYCLIC_INTERVAL_SEQUENCE") or None,
        confirm=(a.get("CONFIRM") or "0") == "1",
        retro=(a.get("RETRO") or "0") == "1",
        timezone=a.get("TIMEZONE") or None,
    )


class ControlMXmlParser:
    def __init__(self) -> None:
        self.workspace = ControlMWorkspace()
        self._tags: Counter[str] = Counter()

    def parse_files(self, paths: list[str | Path]) -> ControlMWorkspace:
        for p in paths:
            self.parse_file(p)
        self.workspace.tag_counts = dict(self._tags)
        log.info("Parseo completo: %d folders, %d jobs", len(self.workspace.folders), len(self.workspace.jobs))
        return self.workspace

    def parse_file(self, path: str | Path) -> None:
        path = Path(path)
        log.info("Leyendo %s", path)
        root = ET.parse(path).getroot()
        self.workspace.source_files.append(str(path))
        for el in root.iter():
            self._tags[_local(el.tag)] += 1
        if _local(root.tag) in FOLDER_TAGS:
            self._parse_folder(root, str(path))
        else:
            for child in root:
                if _local(child.tag) in FOLDER_TAGS:
                    self._parse_folder(child, str(path))
                else:
                    self._warn(f"{path.name}: etiqueta de primer nivel no soportada <{_local(child.tag)}>")

    def _warn(self, msg: str) -> None:
        log.warning(msg)
        self.workspace.parse_warnings.append(msg)

    def _parse_folder(self, el: ET.Element, source: str, parent: str | None = None) -> None:
        a = el.attrib
        name = a.get("FOLDER_NAME") or a.get("TABLE_NAME") or a.get("JOBNAME") or "?"
        full_name = f"{parent}/{name}" if parent else name
        if full_name in self.workspace.folders:
            self._warn(f"Folder duplicado {full_name}; se fusionan sus jobs")
            folder = self.workspace.folders[full_name]
        else:
            folder = ControlMFolder(
                name=full_name,
                datacenter=a.get("DATACENTER"),
                order_method=a.get("FOLDER_ORDER_METHOD"),
                platform=a.get("PLATFORM"),
                version=a.get("VERSION"),
                attributes=dict(a),
                source_file=source,
            )
            self.workspace.folders[full_name] = folder
        for child in el:
            tag = _local(child.tag)
            if tag in JOB_TAGS:
                self._parse_job(child, folder, source)
            elif tag in SUB_FOLDER_TAGS:
                self._parse_folder(child, source, parent=full_name)
            elif tag in ("INCOND", "OUTCOND", "ON", "VARIABLE", "SHOUT", "RULE_BASED_CALENDARS"):
                log.debug("Elemento %s a nivel de folder %s (no evaluado)", tag, full_name)
            else:
                self._warn(f"Folder {full_name}: etiqueta no soportada <{tag}>")

    def _parse_job(self, el: ET.Element, folder: ControlMFolder, source: str) -> None:
        a = dict(el.attrib)
        name = a.get("JOBNAME") or "?"
        isn = a.get("JOBISN")
        key = f"{folder.name}/{name}#{isn or len(folder.job_keys) + 1}"
        if key in self.workspace.jobs:
            key = f"{key}.{len(folder.job_keys) + 1}"
        job = ControlMJob(
            key=key,
            job_name=name,
            job_isn=isn,
            folder=folder.name,
            application=a.get("APPLICATION"),
            sub_application=a.get("SUB_APPLICATION"),
            task_type=a.get("TASKTYPE"),
            schedule=_parse_schedule(a),
            description=a.get("DESCRIPTION"),
            parent_folder=a.get("PARENT_FOLDER"),
            node_id=a.get("NODEID"),
            mem_name=a.get("MEMNAME"),
            attributes=a,
            source_file=source,
        )
        for child in el:
            tag = _local(child.tag)
            c = child.attrib
            if tag == "INCOND":
                job.in_conditions.append(Condition(c.get("NAME", ""), ConditionRole.IN, c.get("ODATE") or "ODAT",
                                                   and_or=(c.get("AND_OR") or "A").upper()))
            elif tag == "OUTCOND":
                job.out_conditions.append(Condition(c.get("NAME", ""), ConditionRole.OUT, c.get("ODATE") or "ODAT",
                                                    sign=c.get("SIGN") or "+"))
            elif tag == "ON":
                job.conditional_actions.append(self._parse_on(child))
            elif tag == "VARIABLE":
                job.variables[c.get("NAME", "")] = c.get("VALUE", "")
            elif tag == "SHOUT":
                job.shouts.append(dict(c))
            elif tag == "CONTROL":
                job.controls.append(dict(c))
            elif tag not in KNOWN_JOB_CHILDREN:
                self._warn(f"Job {key}: etiqueta no soportada <{tag}>")
        folder.job_keys.append(key)
        self.workspace.jobs[key] = job

    def _parse_on(self, el: ET.Element) -> ConditionalAction:
        a = el.attrib
        action = ConditionalAction(stmt=a.get("STMT"), code=a.get("CODE"), and_or=a.get("AND_OR"))
        for child in el:
            tag = _local(child.tag)
            c = child.attrib
            if tag == "DOCOND":
                action.do_conditions.append(Condition(c.get("NAME", ""), ConditionRole.DO, c.get("ODATE") or "ODAT",
                                                      sign=c.get("SIGN") or "+", on_code=action.code, on_stmt=action.stmt))
            elif tag == "DOFORCEJOB":
                action.force_jobs.append(ForceJob(c.get("TABLE_NAME", ""), c.get("NAME", ""), c.get("ODATE") or "ODAT",
                                                  c.get("REMOTE")))
            elif tag == "DOACTION":
                action.do_actions.append(c.get("ACTION", ""))
            else:
                if tag not in KNOWN_ON_CHILDREN:
                    self._warn(f"ON {a.get('CODE')}: acción no soportada <{tag}>")
                action.other_actions.append({"type": tag, **c})
        return action


def parse_workspace(paths: list[str | Path] | str | Path) -> ControlMWorkspace:
    if isinstance(paths, (str, Path)):
        paths = [paths]
    return ControlMXmlParser().parse_files(list(paths))
