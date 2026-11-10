# Web TJ Sokol Huštěnovice

Statický web, který zobrazuje zápasy, výsledky, tabulky a střelce všech týmů klubu.

## Struktura

- `web/index.html`, `web/styles.css`, `web/app.js` – samotný web
- `web/data/club.json` – všechna data (týmy, zápasy, tabulky, střelci)
- `scripts/update_data.py` – kontrola a aktualizace dat
- `.github/workflows/update-data.yml` – spouští aktualizaci každých 15 minut

## Úprava dat (dokud není napojení na FAČR)

Upravte `web/data/club.json`:

- odehraný zápas: `"score": [domácí, hosté]`, neodehraný `"score": null`
- datum ve formátu `2026-11-15T14:00:00+01:00`
- až budou data skutečná, změňte `"source": "sample"` na `"manual"` – zmizí žlutý pruh „ukázková data“

Kontrola, že je soubor v pořádku:

```bash
python3 scripts/update_data.py
```

## Barvy klubu

Změníte je v horní části `web/styles.css` (proměnné `--brand`, `--brand-2`, `--accent`).

## Spuštění na počítači

```bash
python3 -m http.server 8765 --directory web
```

Pak otevřete http://localhost:8765.

## Napojení na FAČR

Až FAČR přidělí oficiální přístup, doplní se funkce `fetch_facr()` ve `scripts/update_data.py`
a ve workflow se nastaví `DATA_SOURCE: facr`. Přístupové údaje patří do GitHub Secrets.
