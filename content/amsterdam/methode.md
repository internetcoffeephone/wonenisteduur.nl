---
title: "Methode: grondwaarde, parkeren en OZB in Amsterdam"
---

# Methode

Deze pagina legt uit hoe we de cijfers op [Grond in Amsterdam](/amsterdam/) hebben berekend: welke gegevens, welke aannames, en waar de onzekerheid zit. Alles is na te rekenen. De code staat in de map `pipeline/amsterdam/` van de broncode van deze site, met alle parameters in één bestand (`params.toml`).

<div class="disclaimer">
Alle grondwaarden op deze pagina's zijn <strong>schattingen</strong>, geen officiële waarden. Officiële grondstaffels zijn opgevraagd via een Woo-verzoek; deze kaart wordt bijgewerkt zodra die er zijn.
</div>

## De aanpak in het kort

We volgen de "simplest viable method" van Lars Doucet (Center for Land Economics), aangepast aan Nederlandse open data:

1. **Grondaandeel per buurt.** WOZ-waarde min wat het kost om de woningen opnieuw te bouwen, rekening houdend met hun leeftijd. Wat overblijft is grond.
2. **Trek onzekere buurten naar het stadsgemiddelde.** Hoe minder woningen, hoe zwaarder het stadsgemiddelde meetelt.
3. **Grond per woning** uit de kadastrale kaart. Appartementen delen het perceel van hun gebouw.
4. **Eén grondprijs per buurt:** grondwaarde per woning gedeeld door grond per woning. Iedereen in de buurt krijgt dezelfde prijs per m². Zo heeft een leeg perceel dezelfde grondwaarde als het bebouwde perceel ernaast. Dat is de kern van een grondbelasting.

## Gegevens en licenties

| Gegevens | Wat we eruit halen | Licentie |
|---|---|---|
| CBS Kerncijfers wijken en buurten 2025 (86165NED) | gemiddelde WOZ-waarde per buurt (peildatum 1-1-2024), aantal woningen | CC BY 4.0 |
| CBS Kerncijfers wijken en buurten 2023 (85618NED) | gemiddeld gestandaardiseerd huishoudinkomen per buurt (nieuwste editie met inkomen) | CC BY 4.0 |
| CBS Wijk- en buurtkaart 2025 (via PDOK) | buurtgrenzen | CC BY 4.0 |
| CBS Vierkantstatistieken 100 m, 2023 (via PDOK) | WOZ-waarde per blok, voor de controle op gelijkmatigheid | CC BY 4.0 |
| CBS 83673NED | bouwkosten per m² van nieuwbouwwoningen | CC BY 4.0 |
| CBS 84550NED | landelijke waarde van grond onder woningen | CC BY 4.0 |
| CBS 83642NED | OZB- en parkeeropbrengst van Amsterdam in 2026 | CC BY 4.0 |
| BAG (Kadaster, via PDOK) | per woning: oppervlakte, bouwjaar, gebruiksdoel, status; panden | publiek domein |
| Kadastrale kaart (Kadaster, via PDOK) | perceelgrenzen en -oppervlakte, zonder eigenaren | CC BY 4.0, bron: Kadaster |
| BGT wegdeel (via PDOK) | parkeervlakken en rijbanen | CC0 |
| OpenStreetMap | parkeerterreinen en herkenningspunten (stations, winkelcentra) | ODbL, © OpenStreetMap-bijdragers |
| Gemeente Amsterdam, Verordening Onroerendezaakbelastingen (CVDR72876, versie 20) | OZB-tarief woningen 2026 | vrij van auteursrecht |
| Gemeente Amsterdam, Grondwaardebepaling voor bestaande erfpachtrechten 2021 (Gemeenteblad 2021, 2521) | de gemeentelijke rekenregel voor grondquotes, als controle | vrij van auteursrecht |

**Wat we bewust niet gebruiken:** het WOZ-waardeloket (massaal opvragen is niet toegestaan), WOZ-waarden per adres, eigendomsgegevens uit de Basisregistratie Kadaster, en de afgeschermde WOZ- en erfpachtgegevens van de gemeente. Niets op deze pagina's is herleidbaar tot een individuele eigenaar.

## Stap 1: het grondaandeel per buurt

Per buurt rekenen we:

> grondaandeel = (WOZ-waarde − afgeschreven herbouwkosten) / WOZ-waarde

- **WOZ-waarde:** het CBS-gemiddelde per buurt maal het aantal woningen in de BAG (verblijfsobjecten in gebruik met een woonfunctie). Dat zijn er {{< cijfer "woningen_bag" >}}; het CBS telt er {{< cijfer "woningen_cbs" >}}. Het CBS-gemiddelde is samen €{{< cijfer "woz_som" >}} miljard.
- **Herbouwkosten per m²:** het CBS meet wat nieuwe woningen kosten volgens de bouwvergunning. Voor West-Nederland was dat in {{< cijfer "p_cbs_jaar" >}} gemiddeld {{< cijfer "bouwkosten_cbs" >}} per m², zonder btw (gemiddelde van huur- en koopwoningen). Daar tellen we bij op: {{< cijfer "p_btw" >}} btw, bijkomende kosten (architect, leges, financiering, winst) en een Amsterdamse toeslag (palen, hoogbouw, krappe bouwplaatsen; ook zijn bouwsommen in vergunningen vaak te laag opgegeven). Het CBS zegt niet of het om gebruiks- of bruto vloeroppervlak gaat; de bandbreedte vangt dat op.
- **Afschrijving:** een woning is minder waard dan nieuw, maar nooit niets. Waardefactor = maximaal(restwaarde, 1 − leeftijd / levensduur), met leeftijd = 2024 − bouwjaar.
- **Bodem en plafond:** het grondaandeel ligt tussen {{< cijfer "p_clip_min" >}} (net als de gemeentelijke erfpachtregel) en {{< cijfer "p_clip_max" >}}.

| Parameter | Lage grondwaarde | Midden | Hoge grondwaarde |
|---|---|---|---|
| Bijkomende kosten | {{< cijfer "p_bijkomend_high" >}} | {{< cijfer "p_bijkomend_central" >}} | {{< cijfer "p_bijkomend_low" >}} |
| Amsterdamse toeslag | {{< cijfer "p_toeslag_high" >}} | {{< cijfer "p_toeslag_central" >}} | {{< cijfer "p_toeslag_low" >}} |
| Herbouwkosten per m² (incl. btw) | {{< cijfer "bouwkosten_low" >}} | {{< cijfer "bouwkosten_central" >}} | {{< cijfer "bouwkosten_high" >}} |
| Levensduur (jaar) | {{< cijfer "p_levensduur_low_land" >}} | {{< cijfer "p_levensduur_central" >}} | {{< cijfer "p_levensduur_high_land" >}} |
| Restwaarde gebouw | {{< cijfer "p_restwaarde_low_land" >}} | {{< cijfer "p_restwaarde_central" >}} | {{< cijfer "p_restwaarde_high_land" >}} |

**Afstemming op het CBS.** Voor de middenvariant hebben we de herbouwkosten zo gekozen dat dezelfde rekenregels, toegepast op alle woningen in Nederland met het landelijke WOZ-gemiddelde, precies het grondaandeel van het CBS opleveren: {{< cijfer "cbs_grondaandeel_nl" >}} in {{< cijfer "cbs_grondaandeel_jaar" >}} (84550NED). Daarvoor moesten de kosten met een factor {{< cijfer "kalibratie" >}} omhoog, tot {{< cijfer "bouwkosten_central" >}} per m². De lage en hoge variant geven landelijk {{< cijfer "nl_check_low" >}} en {{< cijfer "nl_check_high" >}}; het CBS-cijfer ligt daartussen.

**Krimp naar het stadsgemiddelde.** Een buurt met weinig woningen geeft een onzekere schatting. Daarom mengen we het buurtcijfer met het stadsgemiddelde: gewicht = n / (n + {{< cijfer "p_krimp_k" >}}), met n het aantal woningen. Een buurt met 1.000 woningen telt voor {{< cijfer "p_gewicht_1000" >}} mee, een buurt met 100 woningen voor {{< cijfer "p_gewicht_100" >}}.

**Buurten zonder eigen schatting.** Buurten met minder dan {{< cijfer "p_min_woningen" >}} woningen krijgen geen eigen grondprijs. Dat geldt ook voor buurten waar het CBS-gemiddelde niet past bij de woningen in de BAG: een WOZ-waarde per m² onder {{< cijfer "p_min_woz_m2" >}} van het stadsgemiddelde (studenten- of tijdelijke woningen die als complex zijn getaxeerd), of een CBS-telling die meer dan een factor {{< cijfer "p_telling_max" >}} afwijkt van de BAG. Zulke buurten zijn gearceerd op de kaart. In de downloads staat voor hen een wijkgemiddelde, met de kolom `bron_grondprijs` = `wijk`. Van de {{< cijfer "buurten" >}} buurten hebben er {{< cijfer "buurten_eigen" >}} een eigen schatting.

## Stap 2: grond per woning

We verdelen de {{< cijfer "percelen" >}} percelen van de kadastrale kaart over de woningen erop:

1. Elk perceel wordt verdeeld over de panden die erop staan, naar de oppervlakte waarmee elk pand het perceel overlapt. Panden zonder verblijfsobjecten (schuurtjes, garages) tellen niet mee. Percelen zonder pand (straten, parken, water) tellen niet mee.
2. Het deel van een pand wordt verdeeld over de verblijfsobjecten erin, naar vloeroppervlak. Een winkel op de begane grond krijgt zo zijn deel van de grond, en vier appartementen boven elkaar delen de rest.
3. Grote, grotendeels lege percelen (meer dan {{< cijfer "p_cap_m2" >}} m², bijvoorbeeld een openbaar terrein met één gebouw erop) tellen voor hoogstens {{< cijfer "p_cap_maal" >}} keer het bebouwde oppervlak mee. Dat gold voor {{< cijfer "percelen_afgetopt" >}} percelen.

Samen is dat {{< cijfer "woongrond_ha" >}} hectare grond onder woningen.

## Stap 3: grondprijs per buurt

> grondprijs per m² perceel = grondaandeel × gemiddelde WOZ-waarde / gemiddelde grond per woning

Dit is de grondprijs zoals een grondbelasting die zou gebruiken: één prijs per m² voor de hele buurt. Mediaan over alle woningen: {{< cijfer "grondprijs_med_central" >}} per m² ({{< cijfer "grondprijs_med_low" >}}–{{< cijfer "grondprijs_med_high" >}}).

Die prijs hangt sterk af van hoe dicht een buurt bebouwd is en hoe de percelen zijn getekend. In de Bijlmer staan flats op kleine percelen en is het groen eromheen van de gemeente. Daardoor lijkt de grond onder die flats per m² net zo duur als in de Jordaan. Voor de kaart gebruiken we daarom ook:

> grondwaarde per m² woonoppervlak = grondaandeel × gemiddelde WOZ-waarde / gemiddeld woonoppervlak

Die maat zegt alleen iets over de plek, niet over de bebouwing. Mediaan: {{< cijfer "grondwaarde_wo_med_central" >}} per m² woonoppervlak ({{< cijfer "grondwaarde_wo_med_low" >}}–{{< cijfer "grondwaarde_wo_med_high" >}}). Ook de gemeente bepaalt de grondwaarde bij erfpacht mede aan de hand van de toegestane vloeroppervlakte.

## Controles

- **Landelijk grondaandeel.** Zie stap 1: de middenvariant reproduceert het CBS-cijfer, en de lage en hoge variant liggen eromheen.
- **De gemeentelijke erfpachtregel.** Amsterdam bepaalt voor erfpacht de grondwaarde als WOZ-waarde maal de buurtstraatquote: het gemiddelde van (WOZ-waarde − herbouwkosten) / WOZ-waarde in een buurtstraat. Zonder afschrijving, met sloopkosten erbij, minimaal 5% en maximaal 49%. Dat is een beleidskeuze die gunstig is voor erfpachters, geen marktwaarde. Als wij dezelfde regel toepassen (middenkosten plus 5% sloopkosten, geen afschrijving), komt {{< cijfer "bsq_boven_plafond" >}} van de buurten boven de 49% uit.
- **Gelijkmatigheid binnen buurten.** Doucet stelt dat een buurt alleen één grondprijs kan krijgen als hij vrij gelijkmatig is. We hebben per buurt gekeken hoeveel de WOZ-waarde per m² verschilt tussen de blokken van 100 bij 100 meter (CBS-vierkanten, gewogen naar woningen). De mediane variatiecoëfficiënt is {{< cijfer "cv_median" >}}. Slechts {{< cijfer "cv_boven_25" >}} van de {{< cijfer "cv_buurten" >}} buurten met genoeg blokken zit boven 25%. Die staan in de download (`cv_woz_m2`).
- **Woningtype.** We noemen een woning grondgebonden als het pand precies één woning bevat en hoogstens {{< cijfer "p_max_vbo" >}} verblijfsobjecten. Per stadsdeel ligt dat aandeel binnen enkele procentpunten van het CBS-aandeel eengezinswoningen.

## Parkeren

1. **Kandidaten:** {{< cijfer "park_kandidaten_bgt" >}} parkeervlakken op maaiveld uit de BGT (alleen actuele objecten) en {{< cijfer "park_kandidaten_osm" >}} parkeerterreinen uit OpenStreetMap. Uit OpenStreetMap laten we parkeergarages, ondergrondse en daklocaties en parkeerstroken langs de straat weg.
2. **Samenvoegen:** vlakken die elkaar raken worden één stuk.
3. **Straat of terrein:** een stuk geldt als parkeren langs de straat als het kleiner is dan {{< cijfer "p_min_lot" >}} m², als het een smalle strook is (gemiddeld smaller dan {{< cijfer "p_strook_breedte" >}} meter en meer dan {{< cijfer "p_strook_rek" >}} keer zo lang als breed), of als het smal is en voor minstens {{< cijfer "p_rijbaan" >}} van de rand langs een rijbaan loopt. De rest is een parkeerterrein.
4. **Garages en dekken eruit:** terreinen die voor minstens {{< cijfer "p_gebouwd" >}} onder een BAG-pand liggen, tellen niet mee ({{< cijfer "gebouwd_aantal" >}} stuks). Bij gedeeltelijke overlap tellen we alleen het onbebouwde deel.
5. **Waarde:** onbebouwd oppervlak × grondwaarde per m² woonoppervlak van de buurt × {{< cijfer "dichtheid_ref" >}}. Dat laatste is het gemiddelde woonoppervlak per m² woongrond in Amsterdam. Zo waarderen we het terrein alsof het bebouwd wordt als een gemiddelde woonbuurt, en niet als de hoogbouw die er toevallig naast staat. Ligt een terrein in meerdere buurten, dan telt elk deel met zijn eigen buurt.
6. **Namen:** naar type en ligging, zoals "parkeerterrein bij station X" of "bij een supermarkt", met de dichtstbijzijnde straatnaam uit de BAG. Nooit naar eigenaar of merk.

Eigendom is onbekend. Veel van deze grond is van de gemeente, al dan niet in erfpacht.

## OZB-model {#ozb-model}

- **Opbrengst:** €{{< cijfer "ozb_woningen" >}} miljoen OZB woningen in 2026 (CBS 83642NED, voorlopig). Het tarief is {{< cijfer "tarief_officieel" >}} (eigenarenbelasting woningen, Verordening Onroerendezaakbelastingen, ingang heffing {{< cijfer "ozb_tarief_ingang" >}}). De pipeline controleert dat tarief in de tekst van de verordening.
- **Huidige OZB per woning:** de opbrengst verdeeld over de WOZ-waarden. Omdat onze waarden een jaar ouder zijn dan die van de aanslag 2026, komt dat neer op {{< cijfer "tarief_model" >}} van onze waarden.
- **WOZ-waarde per woning:** het buurtgemiddelde, verdeeld naar woonoppervlak (gelijke WOZ-waarde per m² binnen de buurt).
- **Grondwaarde per woning:** de grondwaarde van de buurt, verdeeld naar grond. Per buurt en woningtype nemen we de mediane grond per m² woonoppervlak, zodat één groot perceel niet de hele buurt bepaalt.
- **Gebouwwaarde per woning:** de rest van de buurtwaarde, verdeeld naar afgeschreven herbouwkosten.
- **Varianten:** alleen grond ({{< cijfer "tarief_A_grond" >}} van de grondwaarde), en grond {{< cijfer "p_verhouding" >}} keer zo zwaar belast als gebouw ({{< cijfer "tarief_B_grond" >}} en {{< cijfer "tarief_B_gebouw" >}}). Beide brengen precies evenveel op als nu.
- **Dekking:** {{< cijfer "woningen_model" >}} woningen ({{< cijfer "woningen_model_pct" >}}), in buurten met een bruikbaar WOZ-gemiddelde.
- **Inkomen:** buurten zijn ingedeeld in vijf groepen met elk ongeveer evenveel woningen, naar het gemiddeld gestandaardiseerd inkomen van huishoudens (CBS Kerncijfers 2023, de nieuwste editie met inkomens per buurt). Het CBS publiceert per buurt geen mediaan inkomen.

Per woning publiceren we niets: dat zijn modeluitkomsten, geen waarnemingen. De downloads gaan over buurten en woningtypen per buurt.

## Beperkingen

- Schattingen op buurtniveau. Een individueel perceel kan flink afwijken.
- Alleen woningen. Voor niet-woningen is geen open WOZ-data.
- Statisch: eerste jaar, huidige bebouwing, geen gedragsverandering.
- Erfpachters betalen al canon. Zonder verrekening wordt hun grond dubbel belast.
- De WOZ-peildatum loopt een jaar achter op de aanslag 2026, en de CBS-gemiddelden lopen achter op nieuwbouw.
- Woonboten en woonwagens zitten wel in het CBS-gemiddelde, maar niet in de grondverdeling.
- De parkeerclassificatie is automatisch. Er zitten fouten in, zoals terreinen die bij een gebouw horen.

## Als de grondstaffels binnenkomen

De gemeente heeft per waardegebied een grondprijs per m² in haar WOZ-model. Als die via het Woo-verzoek beschikbaar komen:

1. Zet ze als `pipeline/amsterdam/input/grondstaffels.gpkg` neer: één vlak per waardegebied, met het veld `grondprijs_m2` (woningen) en `peildatum`.
2. Draai de pipeline opnieuw. Stap A gebruikt dan per buurt de officiële prijs, gemiddeld over de waardegebieden in de buurt naar oppervlak. De kolom `bron_grondprijs` wordt `grondstaffel`. Parkeren en OZB rekenen automatisch mee.
3. Pas de tekst aan: "schatting" wordt "gemeentelijke grondprijs", en de vergelijking tussen schatting en staffel wordt zelf een bevinding.

Staffels voor grondgebonden woningen zijn per m² kavel. Voor appartementen heeft de gemeente vaak geen staffel; daar blijft onze schatting nodig.

## Reproduceren

```bash
cd pipeline/amsterdam
export AMS_CACHE=/pad/naar/cache   # ruwe downloads, enkele GB
uv run 01_fetch.py && uv run 02_prepare.py
uv run 03_land.py && uv run 04_parking.py && uv run 05_ozb.py && uv run 06_publish.py
```

Alle getallen op deze pagina's komen uit `data/amsterdam/cijfers.json`, dat door de laatste stap wordt geschreven.
