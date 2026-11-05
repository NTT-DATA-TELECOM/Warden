"""Interfaz de línea de comandos."""
from __future__ import annotations

import argparse
import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

from .config import load_config
from .parser import parse_workspace
from .report.html_report import write_html
from .report.json_report import build_summary, write_json
from .rules import AuditEngine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
log = logging.getLogger("warden")


def setup_logging(level: str, log_dir: Path, stamp: str) -> Path:
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"controlm_audit_{stamp}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.DEBUG)
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.DEBUG)
    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(fmt)
    sh.setLevel(getattr(logging, level.upper(), logging.INFO))
    root.addHandler(fh)
    root.addHandler(sh)
    return log_file


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="warden",
                                description="Auditoría de mallas Control-M exportadas en XML (solo lectura).")
    p.add_argument("xml", nargs="+", help="Uno o varios XML exportados desde Control-M")
    p.add_argument("--start-date", type=date.fromisoformat, default=date.today(), help="Fecha inicial (YYYY-MM-DD)")
    p.add_argument("--days", type=int, default=None, help="Días a simular (por defecto el de la configuración: 365)")
    p.add_argument("--config", type=Path, default=None, help="Ruta a controlm_rules.yaml")
    p.add_argument("--output-dir", type=Path, default=PROJECT_ROOT / "report")
    p.add_argument("--log-dir", type=Path, default=PROJECT_ROOT / "logs")
    p.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    p.add_argument("--rules", default=None, help="Lista de reglas a ejecutar separadas por coma (p.ej. CTM001,CTM004)")
    p.add_argument("--no-html", action="store_true")
    p.add_argument("--no-json", action="store_true")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    log_file = setup_logging(args.log_level, args.log_dir, stamp)
    t0 = time.perf_counter()

    config = load_config(args.config)
    days = args.days or config.default_days
    missing = [x for x in args.xml if not Path(x).exists()]
    if missing:
        log.error("No existe: %s", ", ".join(missing))
        return 2
    ws = parse_workspace(args.xml)
    rules = [r.strip().upper() for r in args.rules.split(",")] if args.rules else None
    result = AuditEngine(config).run(ws, args.start_date, days, rules)

    outputs = []
    if not args.no_json:
        outputs.append(write_json(result, args.output_dir / f"controlm_audit_{stamp}.json", now))
    if not args.no_html:
        outputs.append(write_html(result, args.output_dir / f"controlm_audit_{stamp}.html", now))

    s = build_summary(result)
    elapsed = time.perf_counter() - t0
    log.info("Auditoría completada en %.1fs", elapsed)
    sev = s["severity"]
    lines = [
        "",
        "CONTROL-M MESH AUDIT",
        f"  Jobs analizados:       {s['jobs']}",
        f"  Folders:               {s['folders']}",
        f"  Dependencias:          {s['dependencies']}",
        f"  Dependencias externas: {s['external_dependencies']}",
        f"  ALTA: {sev['ALTA']}  (causas raíz: {s['root_causes_alta']})   MEDIA: {sev['MEDIA']}   BAJA: {sev['BAJA']}   INFO: {sev['INFO']}",
        f"  Tiempo: {elapsed:.1f}s",
    ] + [f"  -> {o}" for o in outputs] + [f"  -> {log_file}", ""]
    sys.stdout.write("\n".join(lines))
    return 0
