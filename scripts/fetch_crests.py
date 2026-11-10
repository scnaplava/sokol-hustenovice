#!/usr/bin/env python3
"""Stáhne znaky obcí soupeřů z Wikimedia Commons (přes Wikidata, vlastnost P94).

Spouští se ručně, jen když přibude nový soupeř:
    python3 scripts/fetch_crests.py

Výstup:
  web/img/obce/<slug>.png   – znaky obcí
  web/data/crests.json      – přiřazení názvů družstev ke znakům + licence

Skutečná klubová loga mají přednost: stačí je uložit do web/img/kluby/
a zapsat do sekce "overrides" v crests.json – skript je nepřepíše.
"""
from __future__ import annotations

import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "web" / "img" / "obce"
CRESTS_FILE = ROOT / "web" / "data" / "crests.json"
UA = "SokolHustenoviceWeb/1.0 (static club website; one-off crest download)"

# Družstvo (začátek názvu v IS FAČR) -> článek obce na české Wikipedii.
# U společných družstev se bere první obec.
TEAM_TO_MUNICIPALITY = {
    "Babice": "Babice (okres Uherské Hradiště)",
    "Bánov": "Bánov",
    "Bílovice": "Bílovice (okres Uherské Hradiště)",
    "Boršice": "Boršice",
    "Buchlovice": "Buchlovice",
    "Chropyně": "Chropyně",
    "FC Slovácko": "Uherské Hradiště",
    "Hluk": "Hluk",
    "Jalubí": "Jalubí",
    "Javořina": "Slavkov (okres Uherské Hradiště)",  # hraje v Slavkově
    "Kněžpole": "Kněžpole (okres Uherské Hradiště)",
    "Koryčany": "Koryčany",
    "Kostelany": "Kostelany nad Moravou",
    "Kudlovice": "Kudlovice",
    "Kunovice": "Kunovice (okres Uherské Hradiště)",
    "Mařatice": "Uherské Hradiště",  # Mařatice jsou část Uherského Hradiště
    "Morkovice": "Morkovice-Slížany",
    "O. N. Ves": "Ostrožská Nová Ves",
    "Ostr. N. Ves": "Ostrožská Nová Ves",
    "OREL UB": "Uherský Brod",
    "Polešovice": "Polešovice",
    "Prakšice": "Prakšice",
    "St. Město": "Staré Město (okres Uherské Hradiště)",
    "Strání": "Strání",
    "Stříbrnice": "Stříbrnice (okres Uherské Hradiště)",
    "Traplice": "Traplice",
    "Uh. Ostroh": "Uherský Ostroh",
    "Velehrad": "Velehrad",
    "Vlčnov": "Vlčnov",
    "Zlechov": "Zlechov",
    "Šumice": "Šumice (okres Uherské Hradiště)",
}


def fetch(url: str) -> tuple[bytes, str]:
    """Stáhne URL; při 429 (příliš mnoho dotazů) počká a zkusí znovu."""
    for attempt in range(6):
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body, ctype = r.read(), r.headers.get("Content-Type", "")
            time.sleep(2)
            return body, ctype
        except urllib.error.HTTPError as e:
            if e.code != 429 or attempt == 5:
                raise
            time.sleep(int(e.headers.get("Retry-After") or 0) or 15 * (attempt + 1))
    raise RuntimeError("nedosažitelné")


def api(url: str, params: dict) -> dict:
    body, _ = fetch(url + "?" + urllib.parse.urlencode({**params, "format": "json"}))
    return json.loads(body)


def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-")


def coat_of_arms(title: str) -> tuple[str, str] | None:
    """Vrátí (wikidata QID, název souboru znaku) pro článek obce."""
    page = api("https://cs.wikipedia.org/w/api.php", {
        "action": "query", "titles": title, "prop": "pageprops", "redirects": 1,
    })["query"]["pages"]
    p = next(iter(page.values()))
    qid = p.get("pageprops", {}).get("wikibase_item")
    if not qid:
        return None
    ent = api("https://www.wikidata.org/w/api.php", {
        "action": "wbgetclaims", "entity": qid, "property": "P94",
    })
    claims = ent.get("claims", {}).get("P94", [])
    if not claims:
        return None
    return qid, claims[0]["mainsnak"]["datavalue"]["value"]


def file_info(filename: str) -> dict:
    pages = api("https://commons.wikimedia.org/w/api.php", {
        "action": "query", "titles": "File:" + filename, "prop": "imageinfo",
        "iiprop": "url|extmetadata", "iiurlwidth": 160,
    })["query"]["pages"]
    info = next(iter(pages.values()))["imageinfo"][0]
    meta = info.get("extmetadata", {})
    return {
        "thumb": info["thumburl"],
        "page": info["descriptionurl"],
        "license": re.sub(r"<[^>]+>", "", meta.get("LicenseShortName", {}).get("value", "")),
    }


def main() -> int:
    existing = json.loads(CRESTS_FILE.read_text(encoding="utf-8")) if CRESTS_FILE.exists() else {}
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    teams, sources, failed = {}, {}, []
    done: dict[str, str] = {}
    for team, title in TEAM_TO_MUNICIPALITY.items():
        if title in done:
            teams[team] = done[title]
            continue
        prev = existing.get("municipal", {}).get(team)
        if prev and (ROOT / "web" / prev).exists() and prev in existing.get("sources", {}):
            teams[team] = done[title] = prev
            sources[prev] = existing["sources"][prev]
            continue
        try:
            found = coat_of_arms(title)
            if not found:
                failed.append(f"{team} ({title}): znak nenalezen")
                continue
            _, filename = found
            info = file_info(filename)
            body, ctype = fetch(info["thumb"])
            ext = ".jpg" if "jpeg" in ctype else ".svg" if "svg" in ctype else ".png"
            name = slug(title.split(" (")[0]) + ext
            (OUT_DIR / name).write_bytes(body)
            path = f"img/obce/{name}"
            teams[team] = done[title] = path
            sources[path] = {"obec": title, "soubor": info["page"], "licence": info["license"]}
            print(f"  {team:14} -> {title} ({info['license']})")
        except Exception as e:  # noqa: BLE001
            failed.append(f"{team} ({title}): {e}")

    out = {
        "_info": "Znaky obcí soupeřů z Wikimedia Commons. Skutečná klubová loga patří do 'overrides'.",
        "overrides": existing.get("overrides", {}),
        "municipal": teams,
        "sources": sources,
    }
    CRESTS_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for f in failed:
        print("  CHYBÍ:", f, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
