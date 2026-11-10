#!/usr/bin/env python3
"""Aktualizace dat pro web TJ Sokol Huštěnovice.

Spouští se každých 15 minut (viz .github/workflows/update-data.yml).

Zdroj dat určuje proměnná prostředí DATA_SOURCE:
  manual  – (výchozí) data se upravují ručně v web/data/club.json,
            skript je jen zkontroluje a nic nemění
  facr    – stáhne data z oficiálního přístupu FAČR
            (doplní se, až FAČR přidělí přístup a pošle dokumentaci)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "web" / "data" / "club.json"

REQUIRED_TEAM_KEYS = {"id", "name", "matches", "table"}
REQUIRED_MATCH_KEYS = {"date", "home", "away"}
REQUIRED_ROW_KEYS = {"team", "played", "won", "drawn", "lost", "gf", "ga", "points"}


def validate(data: dict) -> list[str]:
    """Vrátí seznam chyb; prázdný seznam znamená, že data jsou v pořádku."""
    errors: list[str] = []
    if "club" not in data or "name" not in data.get("club", {}):
        errors.append("chybí club.name")
    teams = data.get("teams")
    if not isinstance(teams, list) or not teams:
        return errors + ["chybí seznam teams"]
    for t in teams:
        tid = t.get("id", "?")
        if missing := REQUIRED_TEAM_KEYS - t.keys():
            errors.append(f"tým {tid}: chybí {sorted(missing)}")
            continue
        for i, m in enumerate(t["matches"]):
            if missing := REQUIRED_MATCH_KEYS - m.keys():
                errors.append(f"tým {tid}, zápas {i + 1}: chybí {sorted(missing)}")
            try:
                datetime.fromisoformat(m.get("date", ""))
            except ValueError:
                errors.append(f"tým {tid}, zápas {i + 1}: neplatné datum {m.get('date')!r}")
            score = m.get("score")
            if score is not None and (not isinstance(score, list) or len(score) != 2):
                errors.append(f"tým {tid}, zápas {i + 1}: score musí být [domácí, hosté] nebo null")
        for i, r in enumerate(t["table"]):
            if missing := REQUIRED_ROW_KEYS - r.keys():
                errors.append(f"tým {tid}, řádek tabulky {i + 1}: chybí {sorted(missing)}")
    return errors


def fetch_facr(current: dict) -> dict:
    """Stáhne aktuální data z oficiálního přístupu FAČR.

    Až FAČR přidělí přístup (API klíč, adresu a dokumentaci), doplní se sem
    volání jejich rozhraní a převod odpovědi do formátu web/data/club.json.
    Přístupové údaje patří do proměnných prostředí (GitHub Secrets),
    nikdy přímo do kódu.
    """
    raise NotImplementedError(
        "Napojení na FAČR zatím není k dispozici – čeká se na oficiální přístup."
    )


def main() -> int:
    source = os.environ.get("DATA_SOURCE", "manual")
    current = json.loads(DATA_FILE.read_text(encoding="utf-8"))

    if source == "facr":
        new = fetch_facr(current)
        new["source"] = "facr"
        new["updatedAt"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    else:
        new = current

    if errors := validate(new):
        print("Data nejsou v pořádku, soubor se nemění:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1

    if new is not current:
        DATA_FILE.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Data aktualizována ({source}).")
    else:
        print(f"Data zkontrolována, beze změny ({source}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
