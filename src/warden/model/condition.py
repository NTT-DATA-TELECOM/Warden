"""Condiciones y dependencias entre jobs.

La identidad de una condición en Control-M es (NOMBRE, FECHA). La fecha se expresa
mediante ODATE relativo al job (ODAT, PREV, NEXT...) y se resuelve en el simulador;
aquí se conserva tal cual aparece en el XML.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache


class ConditionRole(str, Enum):
    IN = "INCOND"
    OUT = "OUTCOND"
    DO = "DOCOND"


class OdateKind(str, Enum):
    ODAT = "ODAT"
    PREV = "PREV"
    NEXT = "NEXT"
    ANY = "ANY"          # STAT, ****, $$$$: cualquier fecha
    EXPLICIT = "DATE"    # MMDD concreto
    UNKNOWN = "UNKNOWN"


_ANY_ODATES = {"STAT", "****", "$$$$"}


@lru_cache(maxsize=None)
def odate_kind(odate: str | None) -> OdateKind:
    value = (odate or "ODAT").strip().upper()
    if value in ("ODAT", "PREV", "NEXT"):
        return OdateKind(value)
    if value in _ANY_ODATES:
        return OdateKind.ANY
    if len(value) == 4 and value.isdigit():
        return OdateKind.EXPLICIT
    return OdateKind.UNKNOWN


# Valores de ON CODE que Control-M interpreta como finalización correcta.
OK_CODES = {"OK"}


@dataclass(frozen=True)
class Condition:
    name: str
    role: ConditionRole
    odate: str = "ODAT"
    sign: str | None = None      # '+' / '-' en OUTCOND y DOCOND
    and_or: str | None = None    # 'A' / 'O' en INCOND
    on_code: str | None = None   # CODE del ON que dispara un DOCOND
    on_stmt: str | None = None

    @property
    def is_add(self) -> bool:
        return self.role != ConditionRole.IN and (self.sign or "+") == "+"

    @property
    def is_delete(self) -> bool:
        return self.role != ConditionRole.IN and self.sign == "-"

    @property
    def odate_kind(self) -> OdateKind:
        return odate_kind(self.odate)

    @property
    def conditional(self) -> bool:
        """True si la condición solo se genera ante un resultado distinto de OK."""
        return self.role == ConditionRole.DO and (self.on_code or "").strip().upper() not in OK_CODES

    def label(self) -> str:
        sign = f" {self.sign}" if self.sign else ""
        code = f" [ON {self.on_code}]" if self.on_code is not None else ""
        return f"{self.name} ({self.odate}{sign}){code}"


@dataclass(frozen=True)
class Dependency:
    """Arco productor -> consumidor derivado de OUTCOND/DOCOND e INCOND con el mismo nombre."""

    producer: str
    consumer: str
    condition: str
    in_odate: str
    out_odate: str
    source: str                  # OUTCOND | DOCOND
    on_code: str | None = None

    @property
    def conditional(self) -> bool:
        return self.source == ConditionRole.DO.value and (self.on_code or "").strip().upper() not in OK_CODES

    @property
    def same_day(self) -> bool:
        """El productor de la misma fecha lógica satisface al consumidor (para jobs diarios)."""
        return odate_kind(self.in_odate) == odate_kind(self.out_odate) and odate_kind(self.in_odate) != OdateKind.ANY

    @property
    def is_self(self) -> bool:
        return self.producer == self.consumer
