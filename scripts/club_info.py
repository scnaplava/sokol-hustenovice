#!/usr/bin/env python3
"""Do každé složky fotbal/<klub>/ zapíše INFO.md se všemi zjištěnými údaji o klubu.

    python3 scripts/club_info.py
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "fotbal"
TZ = ZoneInfo("Europe/Prague")


def fmt(iso: str) -> str:
    return datetime.fromisoformat(iso).astimezone(TZ).strftime("%d. %m. %Y %H:%M")


def team_section(t: dict, is_ours) -> list[str]:
    lines = [f"### {t['name']} ({t.get('category', '')})", ""]
    comp = t.get("competition", "")
    url = t.get("competitionUrl")
    lines.append(f"- **Soutěž:** [{comp}]({url}) – ročník {t.get('season', '')}" if url else f"- **Soutěž:** {comp}")
    row = next((r for r in t.get("table", []) if is_ours(r["team"])), None)
    if row:
        lines.append(f"- **Tabulka:** {row['position']}. místo z {len(t['table'])}, {row['points']} bodů, "
                     f"skóre {row['gf']}:{row['ga']} ({row['won']}V {row['drawn']}R {row['lost']}P)")
    elif not t.get("table"):
        lines.append("- **Tabulka:** FAČR ji pro tuto soutěž nezveřejňuje")
    now = datetime.now(TZ)
    played = [m for m in t["matches"] if m.get("score")]
    upcoming = [m for m in t["matches"] if not m.get("score") and not m.get("played")
                and datetime.fromisoformat(m["date"]) > now]
    if played:
        m = played[-1]
        lines.append(f"- **Poslední zápas:** {fmt(m['date'])} {m['home']} – {m['away']} "
                     f"{m['score'][0]}:{m['score'][1]}")
    if upcoming:
        m = upcoming[0]
        lines.append(f"- **Příští zápas:** {fmt(m['date'])} {m['home']} – {m['away']}"
                     + (f" (hřiště {m['venue']})" if m.get("venue") else ""))
    venues = sorted({m["venue"] for m in t["matches"] if m.get("venue") and is_ours(m["home"])})
    if venues:
        lines.append(f"- **Domácí hřiště v IS FAČR:** {', '.join(venues)}")
    lines.append(f"- **Zápasů v rozpisu:** {len(t['matches'])} (odehráno {len(played) or sum(1 for m in t['matches'] if m.get('played'))})")
    lines.append("")
    return lines


def write_info(folder: Path) -> None:
    data = json.loads((folder / "data" / "club.json").read_text(encoding="utf-8"))
    crests = json.loads((folder / "data" / "crests.json").read_text(encoding="utf-8"))
    c = data["club"]
    facr = c.get("facr") or {"number": "7220181", "isId": "2173", "match": [c["shortName"]]}
    is_ours = lambda n: any(a in n for a in facr["match"])  # noqa: E731
    logo = c.get("logo") or "img/logo.jpg"
    src = crests.get("sources", {}).get(logo)
    colors = c.get("colors") or {"blue": "#1a5fa8", "navy": "#0a1a33", "yellow": "#f7d117"}

    L = [f"# {c['name']}", ""]
    L += ["![Náhled webu – počítač](nahled-pocitac.png)", ""]
    L += ["## Základní údaje", ""]
    L.append(f"- **Oficiální název:** {c.get('official') or c['name']}")
    L.append(f"- **Číslo klubu FAČR:** {facr['number']}")
    L.append(f"- **ID ve veřejné části IS FAČR:** {facr['isId']}")
    L.append(f"- **V rozpisech FAČR vystupuje jako:** {', '.join(facr['match'])}")
    L.append(f"- **Počet týmů v soutěžích:** {len(data['teams'])}")
    if c.get("founded"):
        L.append(f"- **Založen:** {c['founded']}")
    if c.get("email"):
        L.append(f"- **E-mail klubu:** {c['email']}")
    k = c.get("contact")
    if k:
        L.append(f"- **Kontaktní osoba:** {k.get('name', '')}" + (f" ({k['role']})" if k.get("role") else "")
                 + "".join(f", {k[x]}" for x in ("phone", "email") if k.get(x)))
    L.append(f"- **Data aktualizována:** {fmt(data['updatedAt']) if data.get('updatedAt') else '–'}")
    L.append("")
    L += ["## Týmy", ""]
    for t in data["teams"]:
        L += team_section(t, is_ours)
    L += ["## Vzhled webu", ""]
    if src:
        L.append(f"- **Znak na webu:** znak obce {src['obec'].split(' (')[0]} z Wikimedia Commons "
                 f"([zdroj]({src['soubor']}), licence {src['licence']}). "
                 "Není to klubové logo – po dodání loga klubu ho stačí nahradit.")
    elif logo.endswith(".svg"):
        L.append("- **Znak na webu:** zástupný monogram (znak obce na Wikimedia Commons chybí). Doplnit logo klubu.")
    else:
        L.append(f"- **Znak na webu:** `{logo}` (logo klubu)")
    L.append("- **Barvy** (odvozené ze znaku): " + ", ".join(f"{k} `{v}`" for k, v in colors.items()))
    L.append("")
    L += ["## Co zatím chybí (doplnit od klubu)", ""]
    missing = [("stadium", "adresa hřiště"), ("email", "kontaktní e-mail"), ("facebook", "Facebook / Instagram")]
    for key, label in missing:
        if not c.get(key):
            L.append(f"- {label}")
    if not c.get("founded"):
        L.append("- rok založení")
    if not (logo.startswith("img/logo")) or logo.endswith(".svg"):
        L.append("- skutečné logo klubu")
    r = c.get("recruit")
    if r and not (r.get("phone") or r.get("email")):
        L.append("- kontakt na trenéra mládeže a časy tréninků (sekce Nábor)")
    L.append("- popisy týmů")
    L.append("")
    L += ["## Soubory", "",
          "- `index.html` – web (spustit přes jednoduchý server, viz níže)",
          "- `data/club.json` – data klubu a zápasů (aktualizuje stahovač z IS FAČR)",
          "- `nahled-pocitac.png`, `nahled-mobil.png` – náhled webu",
          "",
          "Spuštění na počítači: ve složce `fotbal` spustit `python3 -m http.server 8766` "
          f"a otevřít http://localhost:8766/{folder.name}/", ""]
    (folder / "INFO.md").write_text("\n".join(L), encoding="utf-8")


def main() -> None:
    for folder in sorted(p for p in OUT.iterdir() if (p / "data" / "club.json").exists()):
        write_info(folder)
        print(f"  {folder.name}/INFO.md")


if __name__ == "__main__":
    main()
