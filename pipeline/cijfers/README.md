# Grond in cijfers: data pipeline

Builds the numbers and charts for [/grond-in-cijfers/](https://wonenisteduur.nl/grond-in-cijfers/)
from official CBS tables plus a few hand-entered figures.

## Run it

From the repository root:

```sh
uv run pipeline/cijfers/build.py            # download fresh CBS data, then build
uv run pipeline/cijfers/build.py --offline  # rebuild from the local cache only
uv run pipeline/cijfers/build.py --datum 2026-10-21  # stamp a specific date
```

The script uses only the Python standard library (PEP 723 header, Python 3.11+).
Downloads go to `pipeline/cijfers/cache/` (gitignored). It writes:

- `data/cijfers.json`: formatted Dutch strings (`tekst`), chart metadata, alt texts and
  data tables (`grafieken`), table metadata (`bronnen`) and provenance (`herkomst`).
- `static/cijfers/<chart>.svg` (692 px wide) and `<chart>-smal.svg` (380 px, for phones).

`bijgewerkt` is the date the numbers last changed. If a run produces the same numbers
as the files on disk, nothing is written, so a scheduled run only makes a diff when CBS
or `handmatig.toml` changed.

Then build the site as usual (`hugo build --gc --minify`).

## How the page uses it

- `{{< cijfer "grond_bbp" >}}` prints one value from `tekst` (an unknown key fails the build).
- `{{< grafiek "grond-bbp" >}}` renders a chart (narrow SVG below 560 px), its alt text and
  a `<details>` table with the underlying numbers.
- `{{< cijfers-bronnen >}}` lists the CBS tables with their last-modified dates.

## Sources

All CBS tables come from the OData API at `https://opendata.cbs.nl/ODataApi/odata/<id>/`
(CC BY 4.0). Codes are CBS dimension keys.

| Table | What | Codes and fields | Periods used |
|---|---|---|---|
| 85953NED | Niet-financiële balansen (current revision, after revisie 2021) | Sector `A044923` (totaal); `A047181` AN211 Grond, `A047184` AN2112 Landbouwgrond, `A047162` AN111 Woningen; `Eindbalans_6` (mln euro) | 1995–2025 (2025 provisional) |
| 84550NED | Same, previous revision, discontinued | `A047182` AN2111A Grond onder woningen, `A047162` AN111 Woningen, `A047181` AN211; `Eindbalans_6`, `VolumeIndex2015100_7` | 1995–2022 (2022 provisional, never finalised) |
| 85879NED | Bbp | `SoortGegevens A045297` (werkelijke prijzen), `BrutoBinnenlandsProduct_2` (mln euro), annual | 1995–2025 (2025 provisional) |
| 83642NED | Gemeentebegrotingen; heffingen | `A047000` OZB woningen, `A047001` OZB niet-woningen, `A046999` totaal; `GemeentelijkeHeffingenIn1000Euro_1`, summed over all gemeenten | `belastingen.jaar` (2026, provisional) |
| 83131NED | CPI (2015=100) | `T001112` alle bestedingen, `CPI_1`, annual average | 2013, 2022 |
| 83625NED | Gemiddelde verkoopprijs bestaande koopwoningen | `NL01`, `GemiddeldeVerkoopprijs_1` | latest year (homepage check only) |

85953NED no longer splits land under dwellings from land under business buildings (the
codes exist but are empty), so the dwelling charts use 84550NED.

Hand-entered figures live in `handmatig.toml`, each with source, URL and retrieval date:

- Miljoenennota 2027 (Sept 2026): overdrachtsbelasting 2026 (tabel 3.1.7.1, EMU-basis),
  budgettair belang hypotheekrenteaftrek and eigenwoningforfait 2026 (tabel 4.3.2).
- Lars Doucet (23 April 2026): US land value ≈ 200% of GDP, South Korea > 500%.
- DNB: Van Hoenselaar & Mink, ESB 2019 (55% of the house price in 2018 is land);
  De Meijier & Hebbink, DNB Analyse 2025 ("bijna 60%", 42% ten years earlier).
- CPB Kerngegevenstabel MEV 2027: bruto modaal inkomen.

Update `handmatig.toml` after each Prinsjesdag. When CBS publishes OZB data for a newer
year the script prints a reminder; bump `belastingen.jaar` and the Miljoenennota amounts
together so all bars stay in the same year.

## Definitions

- **Grond / bbp**: AN211 Grond (end-of-year balance, all sectors) divided by GDP at
  current prices for the same year. AN211 covers land under dwellings, under business
  buildings, and agricultural land. CBS gives no value to land under infrastructure,
  water and nature, and leaves out building land.
- **Grond onder woningen vs. woningen**: AN2111A and AN111 from 84550NED. CBS values land
  under dwellings as a residual: the value of the whole property minus the value of the
  building, which is estimated from past investment minus depreciation.
- **Aandeel grond**: AN2111A / (AN2111A + AN111).
- **"Stenen per eenheid, na inflatie"** (2013 to 2022): value ratio divided by the volume
  index ratio (`VolumeIndex2015100_7`) and by the CPI ratio, minus one. The same for land.
  CPI is an annual average while the balances are end-of-year, so treat it as approximate.
- **Revision check**: AN211 and AN111 for 2022 in 85953NED vs. 84550NED.
- **OZB**: sum over all gemeenten of the budgeted revenue (begrote opbrengst).
- **Hypotheekrenteaftrek**: budgettair belang, i.e. revenue forgone without behavioural
  effects; not additive with the eigenwoningforfait.

## Charts

Static SVG, no JavaScript, system fonts, Dutch labels, source line and date in each file.
Colours follow the site palette, stepped so they pass the dataviz palette checks against
the page background `#fafaf8`: land `#5f8a3f` (sage), buildings and bars `#226198`
(navy hue, lifted into the lightness band). Both clear 3:1 contrast, and the pair passes the
colour-blindness separation checks. Every chart has a data table on the page.

To check the rendering:

```sh
mkdir -p /tmp/cijfers-png
uv run --with cairosvg python -c "import cairosvg, glob, os; [cairosvg.svg2png(url=f, write_to='/tmp/cijfers-png/' + os.path.basename(f)[:-4] + '.png', scale=1.5) for f in glob.glob('static/cijfers/*.svg')]"
```

Note that cairosvg falls back to a wide font (often DejaVu Sans), so text looks a little
larger than in a browser; the layout leaves room for that.

## Safety

Downloaded data is only parsed as JSON. Requests are restricted to the CBS API host,
including `odata.nextLink` pages. Only numbers from the downloads reach the charts;
all text in them is written by the script.

## Scheduled refresh (proposed, not enabled)

A weekly workflow could rerun the pipeline and open a pull request when the numbers
change, so the Dutch text can be checked before it goes live. It needs
"Allow GitHub Actions to create pull requests" in the repository settings.

```yaml
# .github/workflows/cijfers.yaml
name: Refresh grond-in-cijfers
on:
  schedule:
    - cron: "17 6 * * 1"
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
jobs:
  refresh:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v6
      - uses: astral-sh/setup-uv@v7
      - run: uv run pipeline/cijfers/build.py
      - name: Open a pull request if the numbers changed
        env:
          GH_TOKEN: ${{ github.token }}
        run: |
          git diff --quiet -- data/cijfers.json static/cijfers && exit 0
          branch="cijfers/$(date +%Y-%m-%d)"
          git switch -c "$branch"
          git add data/cijfers.json static/cijfers
          git -c user.name="github-actions[bot]" \
              -c user.email="41898282+github-actions[bot]@users.noreply.github.com" \
              commit -m "Update CBS-cijfers"
          git push origin "$branch"
          gh pr create --base main --fill
```
