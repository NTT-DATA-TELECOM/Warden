"""Modelo de workspace, folders y jobs independiente del XML."""
from __future__ import annotations

from dataclasses import dataclass, field

from .condition import Condition
from .schedule import Schedule


@dataclass(frozen=True)
class ForceJob:
    """DOFORCEJOB: ordena (fuerza) un job o un folder completo (NAME='*')."""

    table: str
    name: str
    odate: str = "ODAT"
    remote: str | None = None


@dataclass
class ConditionalAction:
    """Bloque <ON STMT CODE> con sus acciones."""

    stmt: str | None
    code: str | None
    and_or: str | None = None
    do_conditions: list[Condition] = field(default_factory=list)
    force_jobs: list[ForceJob] = field(default_factory=list)
    do_actions: list[str] = field(default_factory=list)          # DOACTION ACTION=OK/NOTOK/SPCYC...
    other_actions: list[dict] = field(default_factory=list)      # DOMAIL, DOSHOUT, desconocidas


@dataclass
class ControlMJob:
    key: str
    job_name: str
    job_isn: str | None
    folder: str
    application: str | None
    sub_application: str | None
    task_type: str | None
    schedule: Schedule
    description: str | None = None
    parent_folder: str | None = None
    node_id: str | None = None
    mem_name: str | None = None
    in_conditions: list[Condition] = field(default_factory=list)
    out_conditions: list[Condition] = field(default_factory=list)
    conditional_actions: list[ConditionalAction] = field(default_factory=list)
    controls: list[dict] = field(default_factory=list)
    shouts: list[dict] = field(default_factory=list)
    variables: dict[str, str] = field(default_factory=dict)
    attributes: dict[str, str] = field(default_factory=dict)
    source_file: str | None = None

    # Accesos directos solicitados en la especificación
    @property
    def days(self) -> str | None:
        return self.schedule.days

    @property
    def months(self) -> dict[int, bool | None]:
        return self.schedule.months

    @property
    def time_from(self) -> str | None:
        return self.schedule.time_from

    @property
    def time_to(self) -> str | None:
        return self.schedule.time_to

    @property
    def max_wait(self) -> int | None:
        return self.schedule.max_wait

    @property
    def shift(self) -> str | None:
        return self.schedule.shift

    @property
    def shift_num(self) -> str | None:
        return self.schedule.shift_num

    @property
    def do_conditions(self) -> list[Condition]:
        return [c for action in self.conditional_actions for c in action.do_conditions]

    @property
    def force_jobs(self) -> list[tuple[ConditionalAction, ForceJob]]:
        return [(a, f) for a in self.conditional_actions for f in a.force_jobs]

    def in_condition_groups(self) -> tuple[list[list[Condition]], bool]:
        """Agrupa las INCOND en grupos AND de alternativas OR.

        Devuelve (grupos, ambiguo). Si todas son 'A' cada condición es un grupo. Las
        condiciones 'O' se agrupan en una única alternativa. Una mezcla de 'A' y 'O'
        sin paréntesis no puede resolverse con certeza y se marca como ambigua.
        """
        conds = self.in_conditions
        ors = [c for c in conds if (c.and_or or "A").upper() == "O"]
        ands = [c for c in conds if (c.and_or or "A").upper() != "O"]
        has_parenthesis = any(c.name.startswith("(") or c.name.endswith(")") for c in conds)
        groups = [[c] for c in ands]
        if ors:
            groups.append(ors)
        ambiguous = has_parenthesis or bool(ors and ands)
        return groups, ambiguous


@dataclass
class ControlMFolder:
    name: str
    datacenter: str | None = None
    order_method: str | None = None
    platform: str | None = None
    version: str | None = None
    attributes: dict[str, str] = field(default_factory=dict)
    job_keys: list[str] = field(default_factory=list)
    source_file: str | None = None

    @property
    def auto_ordered(self) -> bool:
        """Sin FOLDER_ORDER_METHOD el folder no lo ordena ni el New Day ni un User Daily."""
        return bool((self.order_method or "").strip())


@dataclass
class ControlMWorkspace:
    folders: dict[str, ControlMFolder] = field(default_factory=dict)
    jobs: dict[str, ControlMJob] = field(default_factory=dict)
    source_files: list[str] = field(default_factory=list)
    parse_warnings: list[str] = field(default_factory=list)
    tag_counts: dict[str, int] = field(default_factory=dict)

    def jobs_by_name(self) -> dict[str, list[str]]:
        index: dict[str, list[str]] = {}
        for key, job in self.jobs.items():
            index.setdefault(job.job_name, []).append(key)
        return index

    def find_jobs(self, folder: str, name: str) -> list[str]:
        f = self.folders.get(folder)
        if not f:
            return []
        if name in ("*", ""):
            return list(f.job_keys)
        return [k for k in f.job_keys if self.jobs[k].job_name == name]
