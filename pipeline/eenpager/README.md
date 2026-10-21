# Eenpager "Verschuif de OZB van stenen naar grond"

Bron van de A4-eenpager die op [/voorstel/](https://wonenisteduur.nl/voorstel/) staat:
`static/voorstel/eenpager-ozb-grondwaarde.pdf`.

| Bestand | Wat |
|---|---|
| `eenpager.html` | De tekst van de eenpager |
| `eenpager.css` | Opmaak: A4, navy `#2c3e50`, salie `#7a9e5a`, lichte salie `#f0f2ec` |
| `build.sh` | Bouwt de PDF en controleert dat het precies één A4-pagina is |
| `check.py` | De controle: paginatelling, formaat, en een kleuren- en grijswaarden-PNG om naar te kijken |
| `check_wetteksten.py` | Controleert of de wetsteksten die op /voorstel/ worden geciteerd nog woordelijk kloppen |

## Bouwen

Nodig: [uv](https://docs.astral.sh/uv/) en de Pango-bibliotheken die WeasyPrint gebruikt
(op Ubuntu/Debian: `sudo apt install libpango-1.0-0 libpangoft2-1.0-0`).
Het lettertype is Ubuntu Sans (standaard op Ubuntu), met DejaVu Sans als terugval.

```sh
sh pipeline/eenpager/build.sh
```

Dat draait, met vastgepinde versies:

```sh
uv run --no-project --with weasyprint==70.0 weasyprint --pdf-variant pdf/ua-1 eenpager.html ../../static/voorstel/eenpager-ozb-grondwaarde.pdf
uv run --no-project --with pymupdf==1.28.2 python -I check.py ../../static/voorstel/eenpager-ozb-grondwaarde.pdf /tmp/eenpager 110
```

Het script stopt met een foutmelding als de PDF meer dan één pagina heeft of geen A4 is.
Bekijk daarna `/tmp/eenpager.png` en `/tmp/eenpager-grijs.png`: de pagina moet ook in zwart-wit goed leesbaar zijn.
Een waarschuwing over "HarfBuzz-Subset" kun je negeren; WeasyPrint gebruikt dan fontTools.
De PDF is niet byte-voor-byte reproduceerbaar (de lettertype-subsets verschillen per build); commit hem alleen als de inhoud is veranderd.

## Wetteksten controleren

```sh
python3 -I pipeline/eenpager/check_wetteksten.py
```

Haalt de geldende versie van de Grondwet, Gemeentewet en Wet WOZ op uit de officiële BWB-repository
(de bron van wetten.overheid.nl) en vergelijkt elk citaat op /voorstel/ woord voor woord.
Draai dit opnieuw voordat je de pagina rondstuurt, en zeker na 1 januari en 1 juli, wanneer wetswijzigingen vaak ingaan.

## Cijfers op de eenpager

- **62% grond (2022), 42% (2013).** CBS-tabel [84550NED](https://opendata.cbs.nl/statline/#/CBS/nl/dataset/84550NED),
  onderwerp *Eindbalans*, sector *Totaal alle sectoren*: grond onder woningen (`A047182`) gedeeld door grond onder woningen plus woningen (`A047162`).
  2022: 2.044.640 / (2.044.640 + 1.231.710) mln euro = 62,4%. 2013: 658.804 / (658.804 + 897.846) = 42,3%.
  Grond ×3,10 en woningen ×1,37 tussen 2013 en 2022. De tabel is stopgezet; 2022 is het laatste jaar.
- **Baden-Württemberg, ruim 11 miljoen inwoners.** Statistisches Landesamt Baden-Württemberg: 11.238.800 eind 2025.
- **Uitspraak 2026.** Bundesfinanzhof, Urteil vom 22. April 2026, II R 26/24.

Pas bij een nieuwe versie ook de datum onderaan de eenpager aan ("Versie oktober 2026").
