#!/usr/bin/env python3
"""Aktualizace dat pro web TJ Sokol Huštěnovice.

Spouští se každých 15 minut (viz .github/workflows/update-data.yml).

Zdroj dat určuje proměnná prostředí DATA_SOURCE:
  facr    – (výchozí) stáhne zápasy a tabulky z veřejné části IS FAČR
            (is.fotbal.cz/public), která je přístupná bez přihlášení
  manual  – data se upravují ručně ve web/data/club.json,
            skript je jen zkontroluje
"""
from __future__ import annotations

import html
import http.cookiejar
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "web" / "data" / "club.json"

# --- Nastavení klubu -------------------------------------------------------
# Výchozí hodnoty pro TJ Sokol Huštěnovice. Jiný klub si je nastaví
# v club.json v sekci "club.facr": {"number", "isId", "match": [...]}.
DEFAULT_FACR = {
    "number": "7220181",      # číslo klubu ve FAČR
    "isId": "2173",           # vnitřní ID klubu ve veřejné části IS FAČR
    "match": ["Huštěnovice"],  # podle těchto textů se poznají naše družstva
}

BASE = "https://is.fotbal.cz/public/souteze/"
USER_AGENT = "TJSokolHustenoviceWeb/1.0 (klubovy web, aktualizace 1x za 15 min)"
TZ = ZoneInfo("Europe/Prague")

# Soutěže podle prvního písmene kódu soutěže (A3C, C1A, ...).
# Poháry (O, Z, ...) se zatím nezobrazují.
# U přípravek se výsledky nevedou (FAČR je zapisuje jako 0:0), proto se skóre nezobrazuje.
NO_SCORE_CATEGORIES = {"G", "H"}
CATEGORIES = {
    "A": ("muzi", "Muži A", "Dospělí"),
    "B": ("muzi-b", "Muži B", "Dospělí"),
    "C": ("dorost", "Starší dorost", "U19"),
    "D": ("mladsi-dorost", "Mladší dorost", "U17"),
    "E": ("starsi-zaci", "Starší žáci", "U15"),
    "F": ("mladsi-zaci", "Mladší žáci", "U13"),
    "G": ("starsi-pripravka", "Starší přípravka", "U11"),
    "H": ("mladsi-pripravka", "Mladší přípravka", "U9"),
}

REQUIRED_TEAM_KEYS = {"id", "name", "matches", "table"}
REQUIRED_MATCH_KEYS = {"date", "home", "away"}
REQUIRED_ROW_KEYS = {"team", "played", "won", "drawn", "lost", "gf", "ga", "points"}


# --- Kontrola dat ----------------------------------------------------------
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


# --- Stahování z IS FAČR ---------------------------------------------------
class IsClient:
    def __init__(self) -> None:
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar())
        )
        self.opener.addheaders = [("User-Agent", USER_AGENT)]

    def get(self, url: str, data: dict | None = None) -> str:
        body = urllib.parse.urlencode(data).encode() if data else None
        for attempt in range(3):
            try:
                with self.opener.open(url, body, timeout=30) as r:
                    text = r.read().decode("utf-8", errors="replace")
                time.sleep(1)  # šetrně k serveru FAČR
                return text
            except OSError:
                if attempt == 2:
                    raise
                time.sleep(5)
        raise RuntimeError("nedosažitelné")


def clean(fragment: str) -> str:
    text = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def strip_team_no(name: str) -> str:
    """'Huštěnovice (9)' -> 'Huštěnovice'"""
    return re.sub(r"\s*\(\d+\)\s*$", "", name).strip()


def find_competitions(client: IsClient, number: str, is_id: str) -> list[dict]:
    """Vyhledá všechny soutěže klubu v aktuálním ročníku."""
    url = BASE + "prehled-soutezi.aspx?sport=fotbal"
    page = client.get(url)
    form = {
        name: html.unescape(value)
        for name, value in re.findall(r'<input[^>]*name="([^"]+)"[^>]*value="([^"]*)"', page)
        if not name.startswith("ctl00$MainContent$btn")
    }
    for name, body in re.findall(r'<select[^>]*name="([^"]+)"[^>]*>(.*?)</select>', page, re.S):
        m = re.search(r'<option[^>]*selected[^>]*value="([^"]*)"', body) or re.search(r'value="([^"]*)"', body)
        form[name] = m.group(1) if m else ""
    form.update({
        "ctl00$MainContent$OddilBoxClenem$txtCisloKlubu": number,
        "ctl00$MainContent$OddilBoxClenem$hidIdKlubu": is_id,
        "ctl00$MainContent$OddilBoxClenem$hidTypSportu": is_id,
        "__EVENTTARGET": "ctl00$MainContent$btnSearch",
        "__EVENTARGUMENT": "",
    })
    result = client.get(url, form)

    comps = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", result, re.S):
        link = re.search(r'detail-souteze\.aspx\?req=([0-9a-f-]+)[^>]*>(.*?)</a>', row, re.S)
        if not link:
            continue
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        # sloupce: Číslo, Název, Kód, Kategorie, Úroveň, Skupina, Druh, Org. jednotka, Ročník
        code = cells[2] if len(cells) > 2 else ""
        comps.append({
            "req": link.group(1),
            "name": clean(link.group(2)),
            "code": code,
            "category": cells[3] if len(cells) > 3 else "",
            "season": cells[8] if len(cells) > 8 else "",
            "org": cells[7] if len(cells) > 7 else "",
        })
    if not comps:
        raise RuntimeError("V IS FAČR se nenašla žádná soutěž klubu – změnila se stránka?")
    return comps


def parse_matches(page: str) -> list[dict]:
    matches = []
    # Každé kolo začíná nadpisem "N. kolo", za ním následuje tabulka zápasů.
    parts = re.split(r'<h2 class="nadpis">', page)[1:]
    for part in parts:
        rnd = re.match(r"\s*(\d+)\.\s*kolo", part)
        for row in re.findall(r'<tr class="type_[^"]*">(.*?)</tr>', part, re.S):
            cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
            if len(cells) < 5:
                continue
            try:
                dt = datetime.strptime(cells[0], "%d.%m.%Y %H:%M").replace(tzinfo=TZ)
            except ValueError:
                continue
            score = re.match(r"(\d+)\s*:\s*(\d+)", cells[3])
            report = re.search(r'zapas-delegace-report\.aspx\?zapas=([0-9a-f-]+)', row)
            matches.append({
                "round": int(rnd.group(1)) if rnd else None,
                "date": dt.isoformat(),
                "home": strip_team_no(cells[1]),
                "away": strip_team_no(cells[2]),
                "score": [int(score.group(1)), int(score.group(2))] if score else None,
                "venue": cells[4] or None,
                "report": (
                    "https://is.fotbal.cz/public/zapasy/zapas-delegace-report.aspx?zapas="
                    + report.group(1) + "&zapis=1&hidemenu=1"
                ) if report and score else None,
            })
    return matches


def parse_table(page: str) -> list[dict]:
    """Vezme první (celkovou) tabulku soutěže."""
    first = re.search(r"<table class='vysledky-tabulky'>(.*?)</table>", page, re.S)
    if not first:
        return []
    rows = []
    for row in re.findall(r"<tr[^>]*>(.*?)(?=<tr|$)", first.group(1), re.S):
        cells = [clean(c) for c in re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)]
        if len(cells) < 8 or not cells[0].isdigit():
            continue
        gf, ga = (int(x) for x in re.findall(r"\d+", cells[6])[:2])
        rows.append({
            "position": int(cells[0]),
            "team": cells[1],
            "played": int(cells[2]),
            "won": int(cells[3]),
            "drawn": int(cells[4]),
            "lost": int(cells[5]),
            "gf": gf,
            "ga": ga,
            "points": int(cells[7]),
        })
    return rows


def fetch_facr(current: dict) -> dict:
    cfg = {**DEFAULT_FACR, **current.get("club", {}).get("facr", {})}
    aliases = cfg["match"] if isinstance(cfg["match"], list) else [cfg["match"]]
    is_ours = lambda name: any(a in name for a in aliases)  # noqa: E731

    client = IsClient()
    previous = {t["id"]: t for t in current.get("teams", [])}
    teams = []
    used_ids: set[str] = set()
    for comp in find_competitions(client, cfg["number"], cfg["isId"]):
        letter = comp["code"][:1].upper()
        if letter not in CATEGORIES:
            continue  # poháry apod.
        team_id, team_name, category = CATEGORIES[letter]
        detail = client.get(BASE + f"detail-souteze.aspx?req={comp['req']}&sport=fotbal")
        try:
            tables = client.get(BASE + f"tabulky-souteze.aspx?req={comp['req']}&sport=fotbal")
        except urllib.error.HTTPError as e:
            if e.code != 403:
                raise
            tables = ""  # FAČR tabulky některých soutěží (přípravky) nezveřejňuje
        ours = [m for m in parse_matches(detail) if is_ours(m["home"]) or is_ours(m["away"])]
        if not ours:
            continue
        # Béčko / céčko klubu ve stejné kategorii (např. "Strání B") dostane vlastní tým.
        our_names = {n for m in ours for n in (m["home"], m["away"]) if is_ours(n)}
        # Béčko se v IS píše různě: "Strání B", 'Koryčany "B"'
        suffix = next((m.group(1) for n in our_names if (m := re.search(r' "?([B-D])"?$', n))), "")
        if suffix:
            team_id = f"{team_id}-{suffix.lower()}"
            team_name = re.sub(r" A$", "", team_name) + f" {suffix}"
        if team_id in used_ids:  # stejná kategorie ve dvou skupinách (např. přípravky B-1 a B-2)
            group = re.search(r"sk\.\s*(\S+)$", comp["name"])
            team_name += f" ({group.group(1)})" if group else " II"
            n = 2
            while f"{team_id}-{n}" in used_ids:
                n += 1
            team_id = f"{team_id}-{n}"
        used_ids.add(team_id)
        if letter in NO_SCORE_CATEGORIES:
            for m in ours:
                m["played"] = m["score"] is not None
                m["score"] = None
        season = comp["season"]
        prev = previous.get(team_id, {})
        teams.append({
            "id": team_id,
            "name": team_name,
            "category": category,
            "competition": comp["name"],
            "competitionUrl": BASE + f"detail-souteze.aspx?req={comp['req']}&sport=fotbal",
            "season": f"{season}/{int(season) + 1}" if season.isdigit() else season,
            "description": prev.get("description", ""),
            "matches": sorted(ours, key=lambda m: m["date"]),
            "table": parse_table(tables),
            "scorers": prev.get("scorers", []) if current.get("source") != "sample" else [],
        })
        print(f"  {team_name}: {comp['name']} – {len(ours)} zápasů")

    order = [v[0] for v in CATEGORIES.values()]
    teams.sort(key=lambda t: (next((i for i, b in enumerate(order) if t["id"].startswith(b)), 99), t["id"]))
    return {
        "source": "facr",
        "updatedAt": current.get("updatedAt"),
        "club": current["club"],
        "teams": teams,
    }


def strip_timestamp(d: dict) -> dict:
    return {k: v for k, v in d.items() if k != "updatedAt"}


def main() -> int:
    source = os.environ.get("DATA_SOURCE", "facr")
    data_file = Path(sys.argv[1]) if len(sys.argv) > 1 else DATA_FILE
    current = json.loads(data_file.read_text(encoding="utf-8"))

    if source == "facr":
        try:
            new = fetch_facr(current)
        except Exception as e:  # síť, změna stránky…  – stará data zůstanou
            print(f"Stažení z IS FAČR selhalo: {e}", file=sys.stderr)
            return 1
    else:
        new = current

    if errors := validate(new):
        print("Data nejsou v pořádku, soubor se nemění:", file=sys.stderr)
        for e in errors:
            print("  -", e, file=sys.stderr)
        return 1

    if strip_timestamp(new) != strip_timestamp(current):
        new["updatedAt"] = datetime.now(TZ).isoformat(timespec="seconds")
        data_file.write_text(json.dumps(new, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Data aktualizována ({source}).")
    else:
        print(f"Beze změny ({source}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
