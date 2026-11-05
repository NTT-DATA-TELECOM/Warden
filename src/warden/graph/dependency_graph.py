"""Grafo dirigido de dependencias de la malla.

Las dependencias se determinan exclusivamente por coincidencia de nombre de condición entre
OUTCOND/DOCOND (SIGN '+') de un productor e INCOND de un consumidor. El ODATE se conserva en
cada arco y se usa para distinguir dependencias del mismo día de las que cruzan días.

Nodos:
  * job:<clave>       un job (clave FOLDER/JOBNAME#JOBISN)
  * ext:<condición>   condición externa (prefijo/lista configurada, sin productor local)
  * miss:<condición>  condición esperada que nadie genera
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable

import networkx as nx

from ..config import AuditConfig
from ..model import Condition, ConditionRole, ControlMWorkspace, Dependency

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Producer:
    job: str
    condition: Condition

    @property
    def conditional(self) -> bool:
        return self.condition.conditional


def ext_node(cond: str) -> str:
    return f"ext:{cond}"


def miss_node(cond: str) -> str:
    return f"miss:{cond}"


class DependencyGraph:
    def __init__(self, workspace: ControlMWorkspace, config: AuditConfig) -> None:
        self.ws = workspace
        self.config = config
        # Índices
        self.producers: dict[str, list[Producer]] = defaultdict(list)      # cond -> productores (+)
        self.deleters: dict[str, list[Producer]] = defaultdict(list)       # cond -> jobs que la borran (-)
        self.consumers: dict[str, list[tuple[str, Condition]]] = defaultdict(list)  # cond -> (job, INCOND)
        self.forced_by: dict[str, list[str]] = defaultdict(list)           # job forzado -> forzadores
        self.forces: dict[str, list[str]] = defaultdict(list)              # forzador -> forzados
        self.dependencies: list[Dependency] = []
        self.g = nx.DiGraph()
        self._build()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        # Jobs que el New Day / User Daily ordena por sí mismos (no dependen de un DOFORCEJOB).
        self.self_ordered = {
            key for key, job in self.ws.jobs.items()
            if job.schedule.has_criteria and (self.ws.folders.get(job.folder) is None or self.ws.folders[job.folder].auto_ordered)
        }
        for key, job in self.ws.jobs.items():
            self.g.add_node(key, kind="job")
            for c in job.in_conditions:
                self.consumers[c.name].append((key, c))
            for c in job.out_conditions + job.do_conditions:
                (self.producers if c.is_add else self.deleters)[c.name].append(Producer(key, c))
            for action, fj in job.force_jobs:
                for target in self.ws.find_jobs(fj.table, fj.name):
                    self.forced_by[target].append(key)
                    self.forces[key].append(target)
                    self.g.add_edge(key, target, kind="force", conds=[], on_code=action.code)

        for cond, cons in self.consumers.items():
            prods = self.producers.get(cond, [])
            if not prods:
                node = ext_node(cond) if self.config.is_external(cond) else miss_node(cond)
                self.g.add_node(node, kind="ext" if node.startswith("ext:") else "missing", condition=cond)
                for consumer, _ in cons:
                    self.g.add_edge(node, consumer, kind="cond", conds=[cond], same_day=True)
                continue
            for consumer, inc in cons:
                for p in prods:
                    dep = Dependency(p.job, consumer, cond, inc.odate, p.condition.odate,
                                     p.condition.role.value, p.condition.on_code)
                    self.dependencies.append(dep)
                    if dep.is_self:
                        continue
                    data = self.g.get_edge_data(p.job, consumer)
                    if data is None or data.get("kind") == "force":
                        prev_conds = data["conds"] if data else []
                        self.g.add_edge(p.job, consumer, kind="cond", conds=prev_conds + [cond],
                                        same_day=dep.same_day and not dep.conditional,
                                        conditional=dep.conditional, also_force=bool(data))
                    else:
                        data["conds"].append(cond)
                        data["same_day"] = data["same_day"] or (dep.same_day and not dep.conditional)
                        data["conditional"] = data.get("conditional", False) and dep.conditional
        log.info("Grafo: %d nodos, %d arcos, %d dependencias", self.g.number_of_nodes(), self.g.number_of_edges(),
                 len(self.dependencies))

    # ------------------------------------------------------------------ queries
    def job_nodes(self) -> list[str]:
        return [n for n, d in self.g.nodes(data=True) if d.get("kind") == "job"]

    def producers_of(self, cond: str, exclude: str | None = None) -> list[Producer]:
        return [p for p in self.producers.get(cond, []) if p.job != exclude]

    def consumers_of(self, cond: str) -> list[str]:
        return sorted({j for j, _ in self.consumers.get(cond, [])})

    def predecessors(self, key: str) -> list[str]:
        return [n for n in self.g.predecessors(key) if self.g.nodes[n].get("kind") == "job"]

    def successors(self, key: str) -> list[str]:
        return list(self.g.successors(key))

    def ancestors(self, key: str) -> set[str]:
        return {n for n in nx.ancestors(self.g, key) if self.g.nodes[n].get("kind") == "job"}

    def descendants(self, key: str) -> set[str]:
        return nx.descendants(self.g, key)

    def paths(self, source: str, target: str, cutoff: int = 15, limit: int = 20) -> list[list[str]]:
        out = []
        for p in nx.all_simple_paths(self.g, source, target, cutoff=cutoff):
            out.append(p)
            if len(out) >= limit:
                break
        return out

    def isolated_jobs(self) -> list[str]:
        return [n for n in self.job_nodes() if self.g.degree(n) == 0]

    def same_day_graph(self) -> nx.DiGraph:
        """Subgrafo con arcos que deben resolverse dentro de la misma fecha lógica."""
        h = nx.DiGraph()
        h.add_nodes_from(self.job_nodes())
        for u, v, d in self.g.edges(data=True):
            if d.get("kind") == "cond" and d.get("same_day") and self.g.nodes[u].get("kind") == "job":
                h.add_edge(u, v)
        return h

    def self_dependencies(self) -> list[Dependency]:
        return [d for d in self.dependencies if d.is_self]

    # ------------------------------------------------------------------ impacto
    def blocked_closure(self, seed_jobs: set[str] = frozenset(), blocked_conds: set[str] = frozenset(),
                        alive: Callable[[str], bool] | None = None) -> set[str]:
        """Jobs que no pueden ejecutarse si `seed_jobs` no se ejecutan y `blocked_conds` no llegan.

        Respeta alternativas: un job queda bloqueado solo si algún grupo AND de sus INCOND tiene
        todas sus alternativas OR sin ningún productor posible. Un job forzado (DOFORCEJOB) sin
        planificación propia se bloquea si todos sus forzadores lo están.

        `alive(job)` permite un análisis para una fecha concreta: los jobs no planificados ese
        día no cuentan como productores alternativos ni como afectados. Sin `alive` el análisis
        es independiente de la fecha (conservador: un productor posible algún día cuenta).
        """
        blocked: set[str] = set(seed_jobs)
        frontier: list[str] = [s for seed in seed_jobs for s in self.successors(seed)]
        for c in blocked_conds:
            frontier.extend(j for j, _ in self.consumers.get(c, []))
        while frontier:
            cand = frontier.pop()
            if cand in blocked or self.g.nodes[cand].get("kind") != "job":
                continue
            if alive is not None and not alive(cand):
                continue
            # Un candidato no bloqueado ahora se reevalúa si se bloquea otro de sus predecesores.
            if self._is_blocked(cand, blocked, blocked_conds, alive):
                blocked.add(cand)
                frontier.extend(self.successors(cand))
        return blocked - set(seed_jobs)

    def _is_blocked(self, key: str, blocked: set[str], blocked_conds: set[str],
                    alive: Callable[[str], bool] | None) -> bool:
        job = self.ws.jobs[key]
        forcers = self.forced_by.get(key)
        if forcers and key not in self.self_ordered:
            if all(f in blocked or (alive is not None and not alive(f)) for f in forcers):
                return True
        groups, _ = job.in_condition_groups()
        for group in groups:
            if all(self._cond_dead(c.name, key, blocked, blocked_conds, alive) for c in group):
                return True
        return False

    def _cond_dead(self, cond: str, consumer: str, blocked: set[str], blocked_conds: set[str],
                   alive: Callable[[str], bool] | None) -> bool:
        if cond in blocked_conds:
            return True
        prods = self.producers_of(cond, exclude=consumer)
        if not prods:
            return False   # sin productor: no es consecuencia de este bloqueo (lo cubre su propia regla)
        return all(p.job in blocked or (alive is not None and not alive(p.job)) for p in prods)

    def split_impact(self, seeds: set[str], impacted: set[str], blocked_conds: set[str] = frozenset()) -> tuple[list[str], list[str]]:
        direct = set()
        for s in seeds:
            direct.update(n for n in self.successors(s) if n in impacted)
        for c in blocked_conds:
            direct.update(j for j, _ in self.consumers.get(c, []) if j in impacted or not seeds)
        indirect = impacted - direct
        return sorted(direct), sorted(indirect)

    def subgraph(self, roots: list[str], blocked: list[str], affected: list[str], extra_nodes: list[str] = (),
                 max_nodes: int = 80) -> dict:
        """Subgrafo para visualización: raíz, bloqueados directos y afectados indirectos."""
        roles: dict[str, str] = {}
        for n in extra_nodes:
            roles[n] = "external" if n.startswith("ext:") else ("missing" if n.startswith("miss:") else "context")
        for n in roots:
            roles[n] = "root"
        for n in blocked:
            roles.setdefault(n, "blocked")
        for n in affected:
            roles.setdefault(n, "affected")
        nodes = list(roles)[:max_nodes]
        keep = set(nodes)
        edges = []
        for u in nodes:
            for v in self.g.successors(u) if u in self.g else ():
                if v in keep:
                    d = self.g.edges[u, v]
                    edges.append({"from": u, "to": v, "kind": d.get("kind"), "conds": d.get("conds", [])[:3]})
        label = lambda n: (self.ws.jobs[n].job_name if n in self.ws.jobs else n.split(":", 1)[-1])
        return {
            "nodes": [{"id": n, "label": label(n), "role": roles[n],
                       "folder": self.ws.jobs[n].folder if n in self.ws.jobs else None} for n in nodes],
            "edges": edges,
            "truncated": len(roles) > max_nodes,
            "total_nodes": len(roles),
        }
