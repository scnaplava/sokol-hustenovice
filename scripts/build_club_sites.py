#!/usr/bin/env python3
"""Vygeneruje weby pro všechny kluby ze souboru kluby/kluby.json.

Každý klub dostane stejný web jako TJ Sokol Huštěnovice (složka web/),
jen s vlastním jménem, znakem, barvami a daty z IS FAČR.

    python3 scripts/build_club_sites.py            # stáhne data a sestaví weby
    python3 scripts/build_club_sites.py --offline  # jen sestaví z už stažených dat

Výstup: fotbal/<slug>/ (samostatný web pro každý klub, včetně fotbal/hustenovice/)
        fotbal/index.html (přehled všech webů)
"""
from __future__ import annotations

import colorsys
import html
import json
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import fetch_crests  # noqa: E402
import update_data  # noqa: E402

WEB = ROOT / "web"
CONFIG = ROOT / "kluby" / "kluby.json"
DATA_DIR = ROOT / "kluby" / "data"
OUT = ROOT / "fotbal"
CRESTS_FILE = WEB / "data" / "crests.json"
OBCE_DIR = WEB / "img" / "obce"

HOME_CLUB = {"slug": "hustenovice", "match": "Huštěnovice", "logo": WEB / "img" / "logo.jpg"}


# --- Barvy ze znaku ---------------------------------------------------------
def read_pixels(image: Path) -> list[tuple[int, int, int, int]]:
    """Načte pixely obrázku přes macOS `sips` (převod na BMP) – bez dalších knihoven."""
    with tempfile.TemporaryDirectory() as tmp:
        bmp = Path(tmp) / "x.bmp"
        subprocess.run(["sips", "-s", "format", "bmp", "-Z", "80", str(image), "--out", str(bmp)],
                       check=True, capture_output=True)
        b = bmp.read_bytes()
    offset = struct.unpack_from("<I", b, 10)[0]
    w, h = struct.unpack_from("<ii", b, 18)
    bpp = struct.unpack_from("<H", b, 28)[0]
    step = bpp // 8
    row = (w * step + 3) & ~3
    px = []
    for y in range(abs(h)):
        for x in range(w):
            i = offset + y * row + x * step
            bl, g, r = b[i], b[i + 1], b[i + 2]
            a = b[i + 3] if step == 4 else 255
            px.append((r, g, bl, a))
    return px


def hexc(rgb) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, round(c))) for c in rgb)


def mix(rgb, other, t):
    return tuple(a + (b - a) * t for a, b in zip(rgb, other))


def luminance(rgb) -> float:
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def palette_from(image: Path) -> dict:
    counts: Counter = Counter()
    for r, g, b, a in read_pixels(image):
        if a < 128:
            continue
        h, l, s = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if s < 0.35 or l > 0.88 or l < 0.12:
            continue  # bílá, černá, šedá
        counts[(round(h * 24) % 24, round(l * 4))] += 1
    groups = [k for k, _ in counts.most_common()]
    def rgb_of(key):
        h, l = key[0] / 24, key[1] / 4
        r, g, b = colorsys.hls_to_rgb(h, min(max(l, 0.32), 0.55), 0.75)
        return (r * 255, g * 255, b * 255)
    if not groups:
        primary, accent = (26, 95, 168), (247, 209, 23)
    else:
        primary = rgb_of(groups[0])
        far = [k for k in groups[1:] if min(abs(k[0] - groups[0][0]), 24 - abs(k[0] - groups[0][0])) >= 4]
        accent = rgb_of(far[0]) if far else (247, 209, 23)
        if luminance(accent) < 0.25:  # tmavý doplněk by na tmavém pozadí zanikl
            accent = mix(accent, (255, 255, 255), 0.35)
    # Pozadí je vždy tmavé (čitelnost), odvozené od hlavní barvy
    return {
        "blue": hexc(primary),
        "blue-bright": hexc(mix(primary, (255, 255, 255), 0.25)),
        "navy": hexc(mix(primary, (6, 10, 20), 0.82)),
        "navy-2": hexc(mix(primary, (6, 10, 20), 0.68)),
        "yellow": hexc(accent),
        "on-yellow": "#0a1a33" if luminance(accent) > 0.35 else "#ffffff",
    }


# --- Náhradní znak (monogram) ---------------------------------------------
def monogram_svg(text: str, colors: dict) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 120 120">
<circle cx="60" cy="60" r="56" fill="{colors['blue']}" stroke="{colors['yellow']}" stroke-width="6"/>
<text x="60" y="74" text-anchor="middle" font-family="Arial Narrow, Arial, sans-serif" font-weight="700"
 font-size="40" fill="#ffffff">{html.escape(text)}</text></svg>"""


# --- Znaky obcí pro všechny soupeře ----------------------------------------
OKRESY = ["okres Uherské Hradiště", "okres Zlín", "okres Kroměříž", "okres Hodonín", "okres Vsetín"]


PREFIXES = {"FK", "FC", "SK", "TJ", "FA", "HS", "MILO", "Milo", "Sokol", "SOKOL", "TATRAN", "Tatran",
            "Slovan", "SLOVAN", "Spartak", "1.", "AFC", "MFK", "SFK", "WAREX"}
ABBREV = [("O.N.Ves", "Ostrožská Nová Ves"), ("O. N. Ves", "Ostrožská Nová Ves"), ("Ostr. ", "Ostrožská "),
          ("Uh. ", "Uherský "), ("Val. ", "Valašské "), ("St. ", "Staré "), ("Mal.", "Malenovic"),
          (" nVl", " nad Vláří"), (" pH", " pod Hostýnem"), (" n.M.", " nad Moravou")]


def crest_key(name: str) -> str:
    """'Strání B' -> 'Strání', 'Buchlovice/Tupesy' -> 'Buchlovice', 'FK MOHELNICE' -> 'MOHELNICE'"""
    first = name.split("/")[0].strip()
    first = first.split("-dívky")[0].replace('"', "").strip()
    parts = first.split(" ")
    while len(parts) > 1 and parts[0] in PREFIXES:
        parts = parts[1:]
    if len(parts) > 1 and len(parts[-1]) == 1 and parts[-1].isupper():
        parts = parts[:-1]
    return " ".join(parts).strip()


def name_variants(key: str) -> list[str]:
    """Varianty názvu obce pro hledání: rozepsané zkratky, malá písmena, první část před pomlčkou."""
    out = [key]
    expanded = key
    for a, b in ABBREV:
        expanded = expanded.replace(a, b)
    out.append(expanded)
    if expanded.startswith("Uherský "):
        out.append(expanded.replace("Uherský ", "Uherské "))
    if expanded.startswith("Valašské "):
        out += [expanded.replace("Valašské ", "Valašská "), expanded.replace("Valašské ", "Valašský ")]
    if expanded.isupper():
        out.append(expanded.title())
    for v in list(out):
        if "-" in v:
            head = v.split("-")[0].strip()
            out += [head, head.title()]
    seen, res = set(), []
    for v in out:
        if v and v not in seen:
            seen.add(v)
            res.append(v)
    return res


def resolve_municipality(key: str) -> str | None:
    """Najde článek obce na cs.wikipedii, který má znak (Wikidata P94)."""
    for v in name_variants(key):
        for title in [v] + [f"{v} ({o})" for o in OKRESY]:
            try:
                if fetch_crests.coat_of_arms(title):
                    return title
            except Exception:  # noqa: BLE001
                continue
    return None


def ensure_crests(names: set[str]) -> dict:
    crests = json.loads(CRESTS_FILE.read_text(encoding="utf-8"))
    municipal = crests.setdefault("municipal", {})
    sources = crests.setdefault("sources", {})
    known = dict(fetch_crests.TEAM_TO_MUNICIPALITY)
    missing = sorted({crest_key(n) for n in names
                      if not any(n.startswith(k) or crest_key(n).startswith(k) for k in municipal)
                      and "Huštěnovice" not in n})
    for key in missing:
        title = known.get(key) or resolve_municipality(key)
        if not title:
            print(f"  znak nenalezen: {key}")
            continue
        found = fetch_crests.coat_of_arms(title)
        if not found:
            print(f"  znak nenalezen: {key} ({title})")
            continue
        info = fetch_crests.file_info(found[1])
        body, ctype = fetch_crests.fetch(info["thumb"])
        ext = ".jpg" if "jpeg" in ctype else ".svg" if "svg" in ctype else ".png"
        fname = fetch_crests.slug(title.split(" (")[0]) + ext
        (OBCE_DIR / fname).write_bytes(body)
        path = f"img/obce/{fname}"
        municipal[key] = path
        sources[path] = {"obec": title, "soubor": info["page"], "licence": info["license"]}
        print(f"  znak: {key} -> {title} ({info['license']})")
    CRESTS_FILE.write_text(json.dumps(crests, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return crests


# --- Sestavení webu ---------------------------------------------------------
def has_youth(data: dict) -> bool:
    return any(t["id"].split("-")[0] in {"starsi", "mladsi"} or t["id"].startswith(("starsi", "mladsi"))
               for t in data["teams"])


def club_json(cfg: dict, colors: dict, logo: str, shape: str, previous: dict) -> dict:
    club = {
        "name": cfg["name"],
        "official": cfg["official"],
        "shortName": cfg["shortName"],
        "brand": cfg["name"],
        "hero": cfg["hero"],
        "founded": None,
        "logo": logo,
        "logoShape": shape,
        "colors": colors,
        "stadium": "",
        "email": "",
        "facebook": "",
        "tagline": "Zápasy, výsledky a tabulky všech našich týmů na jednom místě.",
        "facr": {"number": cfg["number"], "isId": cfg["isId"], "match": cfg["match"]},
    }
    club.update(previous.get("club", {}).get("manual", {}))  # ruční úpravy klubu mají přednost
    return {"source": "facr", "updatedAt": previous.get("updatedAt"), "club": club,
            "teams": previous.get("teams", [])}


def build_site(cfg: dict, data: dict, crests: dict) -> None:
    dest = OUT / cfg["slug"]
    if dest.exists():
        shutil.rmtree(dest)
    (dest / "data").mkdir(parents=True)
    (dest / "img" / "kluby").mkdir(parents=True)
    for f in ("app.js", "styles.css"):
        shutil.copy(WEB / f, dest / f)
    shutil.copytree(OBCE_DIR, dest / "img" / "obce")
    shutil.copy(HOME_CLUB["logo"], dest / "img" / "kluby" / "hustenovice.jpg")

    # Logo klubu: znak obce, nebo monogram, když znak není
    logo_src = WEB / data["club"]["logo"] if data["club"]["logo"].startswith("img/obce/") else None
    if logo_src and logo_src.exists():
        shutil.copy(logo_src, dest / data["club"]["logo"])
    else:
        (dest / "img" / "logo.svg").write_text(monogram_svg(cfg["shortName"][:2].upper(), data["club"]["colors"]))
        data["club"]["logo"], data["club"]["logoShape"] = "img/logo.svg", "round"

    site_crests = {**crests, "overrides": {"Huštěnovice": "img/kluby/hustenovice.jpg"}}
    (dest / "data" / "crests.json").write_text(json.dumps(site_crests, ensure_ascii=False, indent=2))
    (dest / "data" / "club.json").write_text(json.dumps(data, ensure_ascii=False, indent=2))

    page = (WEB / "index.html").read_text(encoding="utf-8")
    name, short = cfg["name"], cfg["shortName"]
    for old, new in [
        ("TJ Sokol Huštěnovice | Fotbal v Huštěnovicích", f"{name} | Fotbalový klub"),
        ("fotbalového klubu TJ Sokol Huštěnovice", f"fotbalového klubu {name}"),
        ('href="img/logo.jpg"', f'href="{data["club"]["logo"]}"'),
        ('src="img/logo.jpg"', f'src="{data["club"]["logo"]}"'),
        ("Znak TJ Sokol Huštěnovice", f"Znak {name}"),
        (">Sokol Huštěnovice<", f">{html.escape(name)}<"),
        ('<p class="kicker" id="founded-line">', '<p class="kicker" id="founded-line" hidden>'),
        (">T.J. Sokol<", f">{html.escape(cfg['hero'][0])}<"),
        (">Huštěnovice</span></h1>", f">{html.escape(cfg['hero'][1])}</span></h1>"),
        (">TJ Sokol Huštěnovice<", f">{html.escape(name)}<"),
    ]:
        page = page.replace(old, new)
    (dest / "index.html").write_text(page, encoding="utf-8")


def overview(entries: list[dict]) -> None:
    cards = "\n".join(
        f'''<a class="c" href="{e['href']}" style="--b:{e['colors']['blue']};--y:{e['colors']['yellow']}">
  <img src="{e['logo']}" alt=""><span><b>{html.escape(e['name'])}</b><small>{html.escape(e['info'])}</small></span></a>'''
        for e in entries)
    (OUT / "index.html").write_text(f"""<!DOCTYPE html>
<html lang="cs"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Weby klubů – 7. liga, sk. C</title>
<style>
body{{margin:0;font-family:system-ui,sans-serif;background:#0a1a33;color:#e8eef7}}
.w{{max-width:1000px;margin:0 auto;padding:40px 20px}}
h1{{font-size:clamp(28px,5vw,44px);margin:0 0 6px}} p{{color:#93a3bb;margin:0 0 26px}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:14px}}
.c{{display:flex;gap:14px;align-items:center;padding:16px;border-radius:14px;text-decoration:none;color:#fff;
background:linear-gradient(135deg,var(--b),#0a1a33 85%);border:1px solid rgba(255,255,255,.1)}}
.c:hover{{border-color:var(--y)}} .c img{{width:52px;height:52px;object-fit:contain;flex:none}}
.c b{{display:block;font-size:17px}} .c small{{color:#c5d1e3}}
</style></head><body><div class="w"><h1>Weby klubů – 7. liga, sk. C</h1>
<p>Náhledy webů všech klubů soutěže. Data z veřejné části IS FAČR.</p>
<div class="g">{cards}</div></div></body></html>""", encoding="utf-8")


def main() -> int:
    offline = "--offline" in sys.argv
    clubs = json.loads(CONFIG.read_text(encoding="utf-8"))["kluby"]
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(exist_ok=True)

    # 1) Data z IS FAČR
    datas = {}
    for cfg in clubs:
        f = DATA_DIR / f"{cfg['slug']}.json"
        previous = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
        data = club_json(cfg, {}, "", "shield", previous)
        if not offline:
            print(f"{cfg['name']}:")
            try:
                new = update_data.fetch_facr(data)
                if new["teams"] != data["teams"]:
                    new["updatedAt"] = update_data.datetime.now(update_data.TZ).isoformat(timespec="seconds")
                data = new
            except Exception as e:  # noqa: BLE001
                print(f"  stažení selhalo: {e}")
        f.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        datas[cfg["slug"]] = data

    # 2) Znaky obcí pro všechny soupeře
    names = {n for d in datas.values() for t in d["teams"]
             for n in [r["team"] for r in t["table"]] + [m[k] for m in t["matches"] for k in ("home", "away")]}
    crests = ensure_crests(names)

    # 3) Weby
    # Huštěnovice: kopie hlavního webu (web/), ať je každý tým ve vlastní složce
    home = OUT / "hustenovice"
    if home.exists():
        shutil.rmtree(home)
    shutil.copytree(WEB, home)
    entries = [{"href": "hustenovice/index.html", "name": "TJ Sokol Huštěnovice", "info": "hlavní web",
                "logo": "hustenovice/img/logo.jpg", "colors": {"blue": "#1a5fa8", "yellow": "#f7d117"}}]
    for cfg in clubs:
        data = datas[cfg["slug"]]
        title = cfg["obec"]
        key = next((k for k, v in fetch_crests.TEAM_TO_MUNICIPALITY.items() if v == title), None)
        logo = crests["municipal"].get(key or cfg["shortName"]) or crests["municipal"].get(crest_key(cfg["match"][0]))
        colors = palette_from(WEB / logo) if logo else palette_from(WEB / "img" / "logo.jpg")
        data["club"]["colors"], data["club"]["logo"], data["club"]["logoShape"] = colors, logo or "", "shield"
        if not has_youth(data):
            data["club"].pop("recruit", None)
        else:
            data["club"].setdefault("recruit", {
                "title": "Přiveď dítě na fotbal",
                "text": "Hledáme nové kluky i holky do mládežnických týmů. Nemusí umět nic, stačí chuť běhat za míčem. Přijďte se podívat na trénink.",
                "points": ["Pro kluky i holky", "Stačí sportovní oblečení a obuv", "První trénink je nezávazný"],
                "trainings": "", "contactName": "", "phone": "", "email": ""})
        build_site(cfg, data, crests)
        men = next((t for t in data["teams"] if t["id"] == "muzi"), None) or \
            next((t for t in data["teams"] if t["id"].startswith("muzi")), None)
        pos = next((r["position"] for r in (men or {}).get("table", []) if any(a in r["team"] for a in cfg["match"])), None)
        entries.append({"href": f"{cfg['slug']}/index.html", "name": cfg["name"],
                        "info": f"{len(data['teams'])} týmů" + (f" · muži {pos}. místo" if pos else ""),
                        "logo": f"{cfg['slug']}/{data['club']['logo']}", "colors": colors})
        print(f"  web: fotbal/{cfg['slug']}/ ({len(data['teams'])} týmů)")
    overview(entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
