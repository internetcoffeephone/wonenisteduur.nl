---
title: "Grond in Amsterdam"
menus:
  main:
    name: Amsterdam
    weight: 40
---

# Grond in Amsterdam

<p class="ams-lead">Waar zit de waarde van Amsterdam? Hoeveel dure grond ligt er onder parkeerterreinen? En wie gaat meer of minder betalen als de OZB niet meer over huis én grond gaat, maar vooral over de grond? We hebben het uitgerekend voor alle buurten van de stad, met openbare gegevens.</p>

<div class="disclaimer">
<strong>Dit zijn schattingen, geen officiële waarden.</strong> De gemeente publiceert geen grondwaarden. Wij hebben ze afgeleid uit de gemiddelde WOZ-waarde per buurt (CBS) en de bouwkosten van de woningen erop. Bij elke schatting staat een bandbreedte. Officiële grondstaffels zijn opgevraagd via een Woo-verzoek; deze kaart wordt bijgewerkt zodra die er zijn.
</div>

## De belangrijkste cijfers

{{< kerncijfers >}}
€{grondwaarde_central} miljard | van de €{woz_som} miljard WOZ-waarde van alle Amsterdamse woningen zit in de grond: {grondaandeel_central} (bandbreedte {grondaandeel_low} tot {grondaandeel_high})
€{park_waarde_central} miljard | grondwaarde onder {park_ha_gewaardeerd} hectare bovengrondse parkeerterreinen in woonbuurten (€{park_waarde_low}–{park_waarde_high} miljard)
{straat_ha} hectare | parkeervakken langs de straat. Dat is openbare ruimte met een geschatte grondwaarde van €{straat_waarde_central} miljard
{type_grondgebonden_p_A} | OZB voor een typische eengezinswoning als alleen grond belast wordt ({type_grondgebonden_d_A} per jaar). Een typisch appartement: {type_appartement_p_A}
{kw1_p_A} | OZB voor een typische woning in de buurten met de laagste inkomens ({kw1_d_A} per jaar)
{{< /kerncijfers >}}

Wat dit betekent:

- **Bijna alle waarde zit in de grond.** Een Amsterdams huis kost gemiddeld {{< cijfer "woz_gem" >}} (WOZ 2024). Opnieuw bouwen kost een fractie daarvan. De rest betaal je voor de plek.
- **Op dure grond staan auto's.** Bovengrondse parkeerterreinen beslaan {{< cijfer "park_ha" >}} hectare, verspreid over {{< cijfer "park_aantal" >}} terreinen. Daarnaast ligt er {{< cijfer "straat_ha" >}} hectare aan parkeervakken langs de stoep.
- **Een grondbelasting op woningen raakt vooral wie veel grond gebruikt.** Eengezinswoningen met een tuin gaan meer betalen, flats en appartementen meestal minder. Woningen in buurten met lage inkomens gaan er gemiddeld op vooruit; de OZB betaalt wel de eigenaar, niet de huurder.
- **Het gaat om kleine bedragen, en dat is ook een conclusie.** De OZB op woningen is in Amsterdam laag: de mediane woning betaalt {{< cijfer "stad_ozb_nu" >}} per jaar. De grote verschuiving zou zitten bij niet-woningen en onbebouwde grond, en die kunnen we met openbare data nog niet doorrekenen.

---

## 1. Waar zit de grondwaarde?

De kaart laat per buurt zien hoeveel van de woningwaarde grond is, uitgedrukt per vierkante meter woonoppervlak. Zo kun je buurten met hoogbouw en buurten met eengezinswoningen eerlijk vergelijken. In de grachtengordel, de Jordaan, Oud-Zuid, De Pijp en Oud-West is elke vierkante meter woning meer dan €7.000 aan grond waard. In grote delen van Zuidoost en in delen van Nieuw-West, Weesp en Noord is dat minder dan €3.500. De stenen kosten overal ongeveer hetzelfde; het verschil zit in de plek.

{{< kaart soort="grond" >}}
Geschatte grondwaarde per m² woonoppervlak per buurt (middenschatting). Met de knoppen boven de kaart wissel je naar de grondprijs per m² perceel of naar de OZB-verandering. Klik op een buurt voor de bandbreedte. Gearceerd: te weinig woningen of een afwijkend WOZ-gemiddelde voor een eigen schatting.
{{< /kaart >}}

{{< stadsdelen >}}

<p class="ams-klein">Gemiddelden per stadsdeel over buurten met een eigen schatting, gewogen naar het aantal woningen. Het grondaandeel is het deel van de WOZ-waarde dat grond is. "Grond per m² perceel" is de prijs van de grond zelf; die is hoger waar meer woonoppervlak op een perceel staat.</p>

### Hoe zeker is dit?

We rekenen per buurt de WOZ-waarde min wat het kost om de woningen opnieuw te bouwen, rekening houdend met hun leeftijd. Wat overblijft is grond. De onzekerheid zit vooral in de bouwkosten en de afschrijving. Daarom rekenen we met een lage, een midden- en een hoge variant. De belangrijkste controles:

- **Landelijk klopt het.** Dezelfde rekenregels geven voor heel Nederland een grondaandeel van {{< cijfer "nl_check_low" >}} tot {{< cijfer "nl_check_high" >}}. Het CBS schat zelf {{< cijfer "cbs_grondaandeel_nl" >}} ({{< cijfer "cbs_grondaandeel_jaar" >}}). Onze middenschatting is daarop afgestemd.
- **De gemeente rekent zelf ook zo.** Voor erfpacht bepaalt Amsterdam het grondaandeel per buurtstraat als WOZ-waarde min herbouwkosten, zonder afschrijving, met een plafond van 49%. Zelfs met die voorzichtige rekenregel komt {{< cijfer "bsq_boven_plafond" >}} van de buurten boven dat plafond uit.
- **Buurten zijn vrij gelijkmatig.** Binnen een buurt verschilt de WOZ-waarde per m² tussen blokken van 100 bij 100 meter gemiddeld maar {{< cijfer "cv_median" >}}. Eén grondprijs per buurt is dus een redelijke eerste benadering.

Hoe het precies werkt, met alle aannames en bronnen, staat op de [methodepagina](/amsterdam/methode/).

---

## 2. Grond onder parkeerplaatsen

We hebben alle parkeervlakken uit de Basisregistratie Grootschalige Topografie (BGT) en OpenStreetMap samengevoegd. Losse parkeervakken langs de straat zijn apart gehouden, en parkeergarages en -dekken zijn eruit gefilterd. Over blijven {{< cijfer "park_aantal" >}} bovengrondse parkeerterreinen met samen {{< cijfer "park_ha" >}} hectare onbebouwde grond.

{{< kerncijfers >}}
€{park_waarde_central} miljard | grondwaarde onder {park_aantal_gewaardeerd} parkeerterreinen ({park_ha_gewaardeerd} ha) in woonbuurten. Bandbreedte €{park_waarde_low}–{park_waarde_high} miljard
{park_ha_geen_tarief} hectare | parkeerterrein in havengebied, kantoorparken en op bedrijventerreinen. Daar wonen te weinig mensen voor een schatting; deze tellen niet mee in het bedrag
€{parkeerheffingen} miljoen | haalt Amsterdam in 2026 op aan parkeerheffingen. Dat is meer dan de hele OZB (€{ozb_totaal} miljoen)
{{< /kerncijfers >}}

{{< kaart soort="parkeren" >}}
Bovengrondse parkeerterreinen (donkerblauw) op de geschatte grondwaarde per buurt. Ingezoomd zie je de terreinen zelf; uitgezoomd een stip per terrein. Klik op een terrein voor de geschatte grondwaarde.
{{< /kaart >}}

Hoe we een terrein waarderen: we nemen de grondwaarde per m² woonoppervlak van de buurt eromheen, en rekenen alsof het terrein zo dicht bebouwd zou worden als een gemiddelde Amsterdamse woonbuurt ({{< cijfer "dichtheid_ref" >}} m² woonoppervlak per m² grond). Dat is geen plan om er huizen te bouwen. Het laat zien wat de grond op die plek waard is, en wat een grondbelasting zou belasten.

### De twintig waardevolste parkeerterreinen

{{< top20 >}}

<p class="ams-klein">Middenschatting in miljoenen euro's, bandbreedte tussen haakjes. Alleen terreinen in buurten met een eigen schatting. Terreinen zijn benoemd naar ligging en type, niet naar eigenaar. Samen zijn deze twintig goed voor {{< cijfer "top20_aandeel" >}} van de geschatte waarde van alle parkeerterreinen in woonbuurten. <a href="/amsterdam/data/top20_parkeerterreinen.csv">Download als CSV</a>.</p>

**Van wie is die grond?** Dat weten we niet, en dat zoeken we ook niet uit. Eigendom staat in de Basisregistratie Kadaster en die gebruiken we bewust niet. Veel Amsterdamse grond is van de gemeente en uitgegeven in erfpacht. Een deel van deze terreinen is dus al gemeentegrond: daar gaat het niet om belasting, maar om de vraag of dit het beste gebruik van zo'n plek is.

**Parkeren langs de straat is een ander verhaal.** De {{< cijfer "straat_ha" >}} hectare aan parkeervakken langs de stoep is openbare ruimte. Op dezelfde manier gewaardeerd gaat het om ongeveer €{{< cijfer "straat_waarde_central" >}} miljard (€{{< cijfer "straat_waarde_low" >}}–{{< cijfer "straat_waarde_high" >}} miljard) aan grondwaarde. Een grondbelasting raakt die ruimte niet; de vraag is wat de stad ervoor terugvraagt. De parkeerbelasting is daar al een vorm van.

---

## 3. Wie betaalt meer, wie minder?

In 2026 haalt Amsterdam €{{< cijfer "ozb_woningen" >}} miljoen OZB op bij eigenaren van woningen, tegen een tarief van {{< cijfer "tarief_officieel" >}} van de WOZ-waarde. Wij hebben uitgerekend wat er gebeurt als precies hetzelfde bedrag wordt opgehaald, maar dan op basis van de grond:

- **Alleen grond:** {{< cijfer "tarief_A_grond" >}} van de geschatte grondwaarde, niets over het gebouw.
- **Grond {{< cijfer "p_verhouding" >}} keer zo zwaar als het gebouw:** {{< cijfer "tarief_B_grond" >}} van de grondwaarde en {{< cijfer "tarief_B_gebouw" >}} van de gebouwwaarde.

De gemeente krijgt in beide varianten evenveel binnen. Wat verandert is wie het betaalt. De tarieven gelden voor onze geschatte waarden op prijspeil 2024; zie de [methode](/amsterdam/methode/#ozb-model).

{{< grafiek naam="ozb-type" tabel="ozb_type" bijschrift="Mediane verandering per woning per jaar. Grondgebonden: een woning die als enige woning in een pand staat, zoals een rijtjeshuis." >}}

Een typisch appartement merkt bijna niets: {{< cijfer "type_appartement_p_A" >}}. Voor een typische eengezinswoning is de verandering {{< cijfer "type_grondgebonden_p_A" >}}, ofwel {{< cijfer "type_grondgebonden_d_A" >}} per jaar. Logisch: wie een tuin heeft, gebruikt meer grond per vierkante meter woning. Van de eengezinswoningen gaat {{< cijfer "type_grondgebonden_plus10_A" >}} er meer dan 10% op achteruit.

{{< grafiek naam="ozb-aandeel" tabel="ozb_type" bijschrift="Aandeel woningen met een verandering van meer dan 10%, variant alleen grond. Over de hele stad gaat {stad_min10_A} van de woningen meer dan 10% minder betalen en {stad_plus10_A} meer dan 10% meer." >}}

{{< grafiek naam="ozb-inkomen" tabel="ozb_inkomen" bijschrift="Buurten ingedeeld in vijf groepen met elk ongeveer evenveel woningen, naar gemiddeld gestandaardiseerd huishoudinkomen (CBS). Mediane verandering per woning." >}}

Woningen in de buurten met de laagste inkomens gaan er gemiddeld op vooruit: {{< cijfer "kw1_p_A" >}} ({{< cijfer "kw1_d_A" >}} per jaar) voor een typische woning. Daar staan veel flats op relatief weinig grond. In de andere buurten verandert weinig: hooguit een paar procent, ongeveer een tientje per jaar.

Let op twee dingen. Dit gaat over buurten, niet over huishoudens: ook in de buurten met de laagste inkomens gaat {{< cijfer "kw1_plus10_A" >}} van de woningen er meer dan 10% op achteruit. En de OZB op woningen betaalt de eigenaar. In buurten met veel huurwoningen is dat vaak een woningcorporatie of een andere verhuurder. Huurders merken het verschil niet direct, omdat gereguleerde huren niet meebewegen met de OZB.

{{< grafiek naam="ozb-stadsdeel" tabel="ozb_stadsdeel" bijschrift="Mediane verandering per woning per stadsdeel, variant alleen grond." >}}

<figure class="ams-grafiek-fig">
<img class="ams-kaart-fallback" src="/amsterdam/kaart-ozb.png" alt="Kaart van de OZB-verandering voor een typische woning per buurt. Blauw: minder betalen, vooral in Nieuw-West, Zuidoost, Noord en IJburg. Oranje: meer betalen, licht in de binnenstad en Zuid, sterker in enkele buurten met veel eengezinswoningen." width="1200" height="1032" loading="lazy">
<figcaption>OZB-verandering voor een typische woning per buurt, variant alleen grond. Op de interactieve kaart bovenaan kun je per buurt klikken.</figcaption>
</figure>

Twee dingen vallen op. Ten eerste schuift de last binnen buurten meer dan tussen buurten. In een buurt met flats én eengezinswoningen met tuin gaan de eengezinswoningen flink meer betalen en de flats flink minder. Ten tweede gaan de bedragen over tientjes per jaar. De mediane woning betaalt nu {{< cijfer "stad_ozb_nu" >}} OZB. Dat komt doordat Amsterdam zijn OZB vooral bij niet-woningen haalt: €{{< cijfer "ozb_nietwoningen" >}} miljoen in 2026, tegen €{{< cijfer "ozb_woningen" >}} miljoen bij woningen.

---

## 4. Wat deze cijfers niet zeggen

- **Het zijn schattingen.** Er zijn geen openbare grondwaarden per perceel en WOZ-waarden per adres mogen niet massaal worden opgevraagd. Wij werken met buurtgemiddelden. De bandbreedtes staan erbij; de werkelijke waarde van één perceel kan meer afwijken.
- **Alleen woningen.** Voor winkels, kantoren, bedrijven en parkeerterreinen bestaat geen open WOZ-data. Daar zou een grondbelasting het meest veranderen. Juist die verschuiving kunnen we nog niet laten zien.
- **Eerste jaar, zonder gedragsverandering.** We rekenen met de huidige bebouwing. Dat een grondbelasting bouwen aantrekkelijker maakt, zit niet in deze cijfers.
- **Per woning is het een model.** We weten de WOZ-waarde per buurt, niet per adres. We nemen aan dat de WOZ-waarde per m² binnen een buurt gelijk is, en dat elke woning de grond krijgt die bij een typische woning van dat type in die buurt hoort. Uitschieters binnen een buurt zitten er niet in.
- **Erfpacht.** Veel Amsterdammers betalen al canon aan de gemeente voor hun grond, en daarnaast OZB over de volle WOZ-waarde. Een grondbelasting zonder verrekening van de canon zou die grond dubbel belasten. Dat moet in een echte regeling worden opgelost; [ons voorstel](/voorstel/) doet dat naar verhouding van de canon.
- **De WOZ-waarden lopen achter.** De CBS-gemiddelden zijn van 1 januari 2024. De OZB van 2026 is gebaseerd op waarden van een jaar later. Daarom rekenen we met het bedrag dat de gemeente ophaalt, niet met het tarief.
- **Parkeerterreinen zijn automatisch herkend.** Een enkel terrein kan verkeerd zijn ingedeeld, bijvoorbeeld als het bij een gebouw hoort of een P+R-functie heeft. De terreinen in de top twintig hebben we niet ter plekke gecontroleerd.

---

## 5. Wat nu?

De gemeente kán dit nu niet invoeren: de Gemeentewet schrijft één OZB-tarief over de hele WOZ-waarde voor. Eén wetswijziging is genoeg om gemeenten de keuze te geven, budgetneutraal, net zoals ze sinds 2026 zelf mogen kiezen voor een leegstandbelasting.

Tegelijk kan de gemeente nu al doen wat deze pagina laat zien, maar dan beter. In haar WOZ-model rekent ze met grondprijzen per waardegebied: de grondstaffels. Die zijn niet openbaar. We hebben ze opgevraagd met een Woo-verzoek. Zodra ze er zijn, vervangen ze onze schattingen en werken we deze pagina bij.

- **Methode, aannames en bronnen:** [methodepagina](/amsterdam/methode/)
- **Downloads (CSV):** [grondprijs per buurt](/amsterdam/data/buurt_grondprijs.csv), [parkeren per buurt](/amsterdam/data/buurt_parkeren.csv), [OZB per buurt](/amsterdam/data/ozb_buurt.csv), [OZB per buurt en woningtype](/amsterdam/data/ozb_buurt_type.csv)
- **Zit je in de gemeenteraad of doe je onderzoek?** Mail {{< email >}}. We rekenen graag een variant voor je door.

<p class="ams-bronnen">Bronnen: CBS Kerncijfers wijken en buurten 2025 en 2023, CBS 83642NED, 83673NED en 84550NED, CBS Wijk- en buurtkaart 2025 en vierkantstatistieken (CC BY 4.0); Kadaster, Kadastrale kaart via PDOK (CC BY 4.0); BAG (publiek domein); BGT (CC0); © OpenStreetMap-bijdragers (ODbL); gemeente Amsterdam, Verordening Onroerendezaakbelastingen (CVDR72876, versie 2026) en Grondwaardebepaling voor bestaande erfpachtrechten 2021. Bewerking en schattingen: wonenisteduur.nl.</p>
