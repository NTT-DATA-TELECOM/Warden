"""Interpretación del nombre PRODUCTOR-TO-CONSUMIDOR de las condiciones (solo evidencia de consistencia)."""
from __future__ import annotations

from .base import AuditContext


def norm_job(name: str, prefixes: list[str]) -> str:
    name = name.strip().upper()
    for p in prefixes:
        p = p.upper()
        if name.startswith(p):
            return name[len(p):]
    return name


def job_names_index(ctx: AuditContext) -> dict[str, list[str]]:
    """Nombre normalizado -> claves de job."""
    if "norm_names" not in ctx.cache:
        idx: dict[str, list[str]] = {}
        for key, job in ctx.ws.jobs.items():
            idx.setdefault(norm_job(job.job_name, ctx.config.equivalent_job_prefixes), []).append(key)
        ctx.cache["norm_names"] = idx
    return ctx.cache["norm_names"]


def parse_condition_name(ctx: AuditContext, cond: str) -> tuple[str, str] | None:
    """-> (productor, consumidor) normalizados según el nombre, o None si no sigue el patrón."""
    sep = ctx.config.naming_separator
    if sep not in cond:
        return None
    left, right = cond.split(sep, 1)
    names = job_names_index(ctx)
    pref = ctx.config.equivalent_job_prefixes
    if norm_job(left, pref) not in names:
        left = ctx.config.condition_prefix_pattern.sub("", left, count=1)
    if norm_job(right, pref) not in names:
        right = ctx.config.condition_prefix_pattern.sub("", right, count=1)
    return norm_job(left, pref), norm_job(right, pref)
