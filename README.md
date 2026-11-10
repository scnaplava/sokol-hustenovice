# Web TJ Sokol Huštěnovice

Statický web, který zobrazuje zápasy, výsledky, tabulky a týmy klubu.
Data se každých 15 minut stahují z **veřejné části IS FAČR** (is.fotbal.cz/public),
která je přístupná bez přihlášení.

## Struktura

- `web/index.html`, `web/styles.css`, `web/app.js` – samotný web
- `web/img/logo.jpg` – znak klubu
- `web/data/club.json` – všechna data (stahují se automaticky)
- `scripts/update_data.py` – stahovač dat z IS FAČR
- `.github/workflows/update-data.yml` – při každé změně nasadí web na GitHub Pages
- `server/setup.sh` – instalace aktualizace dat na server v Česku (každých 15 minut)

## Aktualizace dat

IS FAČR neodpovídá serverům GitHubu v zahraničí, proto data stahuje malý server v Česku.
Server každých 15 minut spustí `scripts/update_data.py` a při změně nahraje
`web/data/club.json` na GitHub. GitHub pak web sám znovu nasadí.

Instalace na server (Ubuntu/Debian, jako root): `bash setup.sh`, přidat vypsaný klíč
jako Deploy key s právem zápisu v nastavení repozitáře, pak `bash setup.sh --dokoncit`.

## Odkud se berou data

Stahovač podle čísla klubu (7220181) sám najde všechny soutěže klubu v aktuálním ročníku,
takže se v nové sezóně nemusí nic přepisovat. Pro každou soutěž stáhne:

- rozpis a výsledky zápasů (jen zápasy Huštěnovic),
- celkovou tabulku.

Omezení:

- **Přípravky:** FAČR nezveřejňuje jejich tabulky a výsledky (zapisuje 0:0). Web proto
  u přípravek ukazuje jen rozpis a „odehráno“.
- **Poháry** se zatím nezobrazují.
- **Střelci** se zatím nestahují (jsou jen v zápisech o utkání).

## Co se dá upravit ručně

V `web/data/club.json` můžete změnit údaje o klubu (`club` – stadion, e-mail, Facebook,
úvodní věta) a popisy týmů (`description`). Stahovač je při další aktualizaci zachová.

Ruční spuštění stahovače:

```bash
python3 scripts/update_data.py
```

## Barvy klubu

Jsou v horní části `web/styles.css` (proměnné `--blue`, `--navy`, `--yellow`).

## Spuštění na počítači

```bash
python3 -m http.server 8765 --directory web
```

Pak otevřete http://localhost:8765.
