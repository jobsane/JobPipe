# Søknadspakke-prompt: CV-spissing og søknadsbrev
## JobPipe — versjon 2.1
### Kalibrert mot Lars Værland, april 2026

---

## Modellkrav

Denne prompten krever den beste tilgjengelige modellen med lengst mulig tenketid (extended thinking / chain-of-thought). Søknadsbrev-generering er den mest språksensitive delen av hele pipelinen. Bruk o1, o1-pro, Claude Opus eller tilsvarende. Aldri bruk mini/haiku/flash-modeller for dette steget.

---

## Hensikt

Denne prompten styrer genereringen av to dokumenter per jobbsøknad:
1. Spisset CV (tilpasset stillingen og rolle-profil)
2. Søknadsbrev (~250-280 ord, kalibrert mot kandidatens dokumenterte stil)

Søknadsbrevet er den vanskeligste delen å generere riktig. Det skal leses som noe et menneske skrev fordi det hadde noe å si - ikke som en AI som krysset av krav. Det skal fortelle en historie om retning, ikke presentere en liste med kvalifikasjoner.

---

## STEG 0: SPRÅKKALIBRERING (kjøres før alt annet)

**Formål:** Tvinge AI-en til å forstå kandidatens stemme FØR den skriver noe.

**Gjør følgende:**

Les kalibreringsbrevet (`configs/calibration/soknadsbrev_arendal_2026.txt`) og svar på dette refleksjonsspørsmålet:

> "Hvorfor tror du Lars ikke bruker ordet 'jeg' så mye i tidligere søknader?"

Svar grundig og internt (ikke i output). Poenget er at AI-en skal forstå:
- Lars unngår ikke "jeg" fordi han er formell eller depersonalisert
- Han unngår det fordi fokuset skal ligge på verdien for arbeidsgiver, ikke på kandidaten selv
- Når han bruker "jeg" er det bevisst: "jeg søker denne stillingen", "jeg bor i Arendal" - aldri som pynt
- Språket er employer-first av overbevisning, ikke av stilistisk preferanse

Denne refleksjonen er ikke optional. Den kalibrerer hele den språklige tilnærmingen for resten av genereringen. Hopp aldri over den.

---

## INNDATA SOM KREVES

Alle fire må være tilgjengelige før generering starter:

| Inndata | Kilde | Merk |
|---|---|---|
| Stillingsannonse (fullstendig tekst) | Hentet fra NAV/Finn/arbeidsgiver | Les HELE annonsen, ikke bare kravlisten |
| Master-CV | `profile_pack.md` | Inneholder rolle-tagger og all erfaring |
| Triage-resultat | `01_triage.json` fra pipeline | Brukes til å bekrefte rollelogikk og gap-vurdering |
| Kalibreringsbrev | `configs/calibration/soknadsbrev_arendal_2026.txt` | Gullstandard for stil, lengde og tone |

---

## STEG 1: ANNONSE-DEKODING

**Formål:** Forstå hva jobben egentlig handler om, ikke bare hva den sier.

**Gjør følgende:**

Les annonsen to ganger. Første gang for å forstå overflaten (tittel, krav, oppgaver). Andre gang for å svare på:

- Hva er arbeidsgivers **faktiske problem** de ansetter for å løse? (Ikke tittelen - det underliggende behovet)
- Hva skjer hvis de ansetter feil person? Hva risikerer de?
- Hvilke **nøkkelord og formuleringer** bruker arbeidsgiveren om rollen? (Disse skal speiles direkte i søknadsbrevet)
- Er det **implisitte krav** som ikke er listet under "Kvalifikasjoner"? (F.eks. kulturell pasning, sektorkunnskap, lokal tilknytning)
- Hva er **organisasjonskonteksten**? Rapporteringsline, størrelse, sektor, fase (vekst/omstilling/stabilisering)?
- Er dette en **ny stilling** eller en **erstatning**? Hva forteller det om situasjonen?

**Output fra steg 1 (intern, ikke i søknadsbrevet):**
```
ANNONSE-ANALYSE:
Faktisk problem: [...]
Risiko ved feil ansettelse: [...]
Nøkkelord som MÅ speiles: [...]
Implisitte krav: [...]
Organisasjonskontekst: [...]
```

---

## STEG 2: KANDIDAT-TIL-ANNONSE-MAPPING

**Formål:** Fastslå hva som matcher, hva som er svakt og hva som er gap.

**Bruk rolle-taggene i master-CV.** Identifiser hvilken primær rolleprofil som er relevant:
- `[ROLLE: PRODUKT]` - Produkteierskap, backlog, roadmap
- `[ROLLE: STRATEGI]` - Strategi, forretningsutvikling, endringsledelse
- `[ROLLE: PROSJEKT]` - Prosjektledelse, leveranse
- `[ROLLE: IT]` - Teknisk forvaltning, tjenestedesign
- `[ROLLE: CXM]` - Kundereise, markedsføring

**Kartlegg følgende:**

**Direkte match** (kandidaten har dokumentert erfaring):
- Liste hvert krav fra annonsen med direkte kobling til erfaring
- Vær presis: hvilken stilling, hvilket prosjekt, hvilket resultat

**Kontekstuell match** (overførbar kompetanse fra annet domene):
- Identifiser hvor privat sektor-erfaring løser kommunal/offentlig sektor-utfordring
- Formuler overføringsverdien, ikke bare erfaringen

**Gap** (krav uten dekning):
- List hvert gap eksplisitt
- Vurder: Kritisk gap (knock-out) eller mykbart gap?
- Identifiser mykningsstrategi for hvert gap

**Særlige kontekstmarkører for offentlig sektor:**
- Vegårshei kommune-perioden (politisk sekretariat, arkiv, digitalisering av byggesaksarkiv, DDØ-intranett) brukes aktivt der kandidatens offentlig sektor-erfaring er et gap mot kommunal/offentlig arbeidsgiver
- IKT Agder-kjennskap er relevant for alle Agder-kommuner
- Meddommer ved Agder tingrett (2021-2025) er lokal forankring, ikke en jobb

**Output fra steg 2 (intern):**
```
MAPPING:
Direkte match: [...]
Kontekstuell match: [...]
Gap og strategi: [...]
Aktiveres Vegårshei: ja/nei
Aktiveres IKT Agder: ja/nei
```

---

## STEG 3: GAP-PLAN OG NARRATIV BUE

**Formål:** Bestem hvordan hvert gap addresseres, og finn den narrative buen som binder brevet sammen.

**Regler for gap-håndtering:**

| Gap-type | Strategi |
|---|---|
| Manglende bransjekunnskap (privat vs. offentlig) | Vær ærlig: kommersiell disiplin er noe offentlig sektor trenger mer av |
| Manglende kommunal erfaring | Aktiver Vegårshei-perioden, men som noe som ga "mersmak" - ikke som en unnskyldning |
| Manglende formell ledelseserfaring | Bruk prosjektledelse og tverrfaglig koordinering som funksjonelt lederskap |
| Manglende spesifikk teknologi | BI-modulene som læringsevne-bevis |
| Karrierepivot (nytt domene) | BI Executive Master som dokumentert, treårig strategisk valg |

**Viktig om gap: Vær ærlig, ikke defensiv.** Lars skriver "tette hull i kompetansen min" - ikke "reframe som styrke". Ærlighet om gap med en konkret plan for å dekke dem er sterkere enn å late som gapet ikke finnes.

**Narrativ bue (obligatorisk konsept):**
Søknadsbrevet skal fortelle en historie med retning. Ikke en liste med kvalifikasjoner, men en sammenhengende linje fra erfaring via utdanning til denne stillingen.

Eksempel på den narrative buen i kalibreringsbrevet:
1. Kjernekompetansen er bygget bevisst mot det annonsen etterspør
2. Brownells bygget den kommersielle disiplinen (portefølje, gevinst, tverrfaglig)
3. Vegårshei ga mersmak for offentlig sektor og var starten på løpet mot ny utdanning
4. BI-modulene over tre år er retningen gjort konkret - ikke tilfeldig
5. Bor i Arendal, søker for å bidra på sikt

Buen skal tilpasses per stilling, men den underliggende logikken er alltid: erfaring + innsikt = retning = denne stillingen.

**Motivasjon:**
Motivasjon er ikke noe som demonstreres i stillhet. Lars sier det eksplisitt: "Det er selve grunnen til at jeg søker denne stillingen." Men det er troverdig fordi det er bygget opp av fakta (treårig BI-løp, lokalt bosted, Vegårshei-erfaring). Regelen er: si det direkte, men bare hvis du har bevisene som underbygger det.

**"Krysningspunktet" (Lars sitt personlige rammeverk):**
Lars beskriver sin kjernekompetanse som arbeid i "krysningspunktet organisasjon, teknologi, tjenester og folk". Dette er hans personlige branding og skal brukes der det er naturlig - særlig i åpningsavsnittet. Det er ikke en frase man setter inn overalt, men et rammeverk som binder kompetansen sammen.

**Geografi og flyttevillighet:**
Lars bor i Arendal. For stillinger i Arendal/Agder er lokal forankring et argument. For stillinger utenfor regionen (Oslo, Drammen, Porsgrunn, etc.) skal brevet ALLTID inneholde en setning om at kandidaten er villig til å flytte. Ikke gjør et nummer ut av det - bare nevn det som en praktisk realitet. Eksempel: "Er villig til å flytte til [sted] for riktig stilling." Plasseres naturlig i avsnitt 4 (forankring) som erstatning for lokal forankring-setningen.

---

## STEG 4: CV-SPISSING

**Formål:** Generer tilpasset CV basert på primær rolleprofil og annonse.

**Regler:**

**Format:**
- Maks 2 A4-sider
- Norsk, med mindre annonsen er på engelsk
- Punktlister og tydelige overskrifter for ATS-match
- Profil-ingress: 2-3 setninger, employer-first

**Innhold:**
- Ta kun med [ROLLE: X]-merket innhold relevant for primærrollen
- Kjernekompetanser: 6-8 punkter som matcher annonsens nøkkelord direkte
- Erfaringer: beskriv resultater, ikke arbeidsoppgaver
- Utdanning: alltid inkludere BI Executive Master of Management-modulene

**BI-utdanning - obligatorisk format i CV:**
```
[Modulnavn]
Executive Master of Management, Handelshøyskolen BI
[Periode]
[Kort beskrivelse av innhold - maks 1 linje]
```

Modulnavn (eksakt stavemåte):
- Endringsledelse (sep. 2025 - jun. 2026)
- Markedsstrategi (okt. 2024 - jun. 2025)
- Strategisk forretningsutvikling og innovasjon (sep. 2023 - jun. 2024)

**Aldri inkluder:** karakterer, grades, karakter A eller tilsvarende

**Vegårshei kommune:**
- Inkluder i CV kun dersom offentlig sektor er primær kontekst for rollen
- Tittel: Konsulent, politisk sekretariat og arkiv
- Beskriv digitaliseringsprosjektene: byggesaksarkiv og DDØ-intranett

---

## STEG 5: SØKNADSBREV

**Formål:** Fortell historien som CVen ikke kan fortelle.

### 5.1 Hva søknadsbrevet skal gjøre (og ikke gjøre)

| Skal | Skal ikke |
|---|---|
| Fortelle en sammenhengende historie med retning | Gjenta CV-innhold som liste |
| Si eksplisitt hvorfor denne stillingen | Demonstrere motivasjon i stillhet |
| Speile nøkkelord fra annonsen | Bruke annonsens ord uten kontekst |
| Være ærlig om gap og plan for å tette dem | Late som gap ikke finnes |
| Vise lokal/kontekstuell forståelse | Overdrive lokal tilknytning (aldri "barna mine") |
| Bruke "jeg" bevisst og naturlig | Unngå "jeg" mekanisk |

### 5.2 Lengde og struktur

**Lengde:** 250-280 ord (eksklusiv header og signatur)

**Obligatorisk struktur - fem deler:**

**Avsnitt 1: Åpning (3-5 setninger)**
- Start med arbeidsgivers behov, speil eksakt språk fra annonsen
- Koble det umiddelbart til "min kjernekompetanse" / "krysningspunktet organisasjon, teknologi, tjenester og folk"
- Si eksplisitt at kompetansen er bygget bevisst mot dette
- Si eksplisitt at dette er grunnen til at du søker
- Tonen er direkte og personlig, ikke klinisk

**Avsnitt 2: Kjernekompetanse - Brownells (2-3 setninger)**
- Brownells/hovederfaring presentert som det som bygget kompetansen annonsen etterspør
- Bruk annonsens egne ord: "porteføljestyring", "gevinstrealisering", "tverrfaglig koordinering" - tilpass per stilling
- Avslutt med en setning om at kommersiell disiplin er verdifullt i ny kontekst
- Kort og argumentativt, ikke CV-oppramsing

**Avsnitt 3: Kontekstuell erfaring - Vegårshei (3-4 setninger, aktiveres for offentlig sektor)**
- Introduser lett: "for øvrig ikke helt ukjent terreng" eller tilsvarende
- Nevn konkrete prosjekter (byggesaksarkiv, DDØ-intranett)
- Koble til hva det ga: innsikt i kommunal kompleksitet OG mersmak
- Avslutt med broen til BI: "Og starten på løpet som slutter med ny utdanning"
- Denne setningen er NARRATIVBROEN - den binder erfaring til utdanning

**Avsnitt 4: BI-pivot og forankring (3-4 setninger)**
- Programnavnet først: "Executive Master of Management fullføres nå..."
- Modulene listet direkte: "består av modulene [X], [Y] og [Z] ved Handelshøyskolen BI"
- "Utdannelsen er ikke tilfeldig. Det er retningen, gjort konkret over tid"
- Ærlig om gap: "for å bli bedre på det jeg kan fra før og tette hull i kompetansen min"
- **Lokal stilling (Arendal/Agder):** "Jeg bor i [sted], har nærmeste familie i området"
- **Stilling utenfor regionen:** "Er villig til å flytte til [sted] for riktig stilling" - alltid inkludert, aldri utelatt
- Avslutt: "søker denne stillingen for å bidra på sikt, ikke som et mellomsteg"

**Avslutning (1 setning):**
- "Ser frem til en samtale om hvilken verdi jeg kan tilføre [arbeidsgiver]."
- Alternativ: "Tar gjerne en samtale om hva dette kan bety i praksis."
- Rolig, direkte, ikke servil

### 5.3 Stil og språk

**Lars sin stemme - personlig, direkte, varm:**
- "Jeg" brukes bevisst og naturlig - ikke unngått, men heller ikke i annenhver setning
- Tonen er samtalende: "for øvrig", "mersmak", "ikke helt ukjent terreng"
- Korte, rytmiske setninger blandet med lengre resonnementer
- Ærlig og direkte om både styrker og gap
- Moden og reflektert uten å være selvhøytidelig

**Hva som skiller Lars sin stemme fra AI-generert tekst:**
- AI skriver: "Kompetansen er godt tilpasset det" / Lars skriver: "Det er selve grunnen til at jeg søker denne stillingen"
- AI skriver: "Direkte overførbare arbeidsmekanismer" / Lars skriver: "Kommersiell disiplin rundt riktig måloppnåelse"
- AI skriver: "Kandidaten er lokalt forankret" / Lars skriver: "Jeg bor i Arendal"
- AI skriver: "Det er en kombinasjon som sjelden finnes samlet" / Lars skriver: "Stillingen fremstår som spennende, utfordrende og i kjernen av den kompetansen jeg har bygget opp"

**Mønsteret:** Lars er mer direkte, mer personlig, mer ærlig. Han forteller deg hva han mener uten å kle det i nøytrale formuleringer. AI-en tenderer mot å gjemme seg bak passive konstruksjoner og abstrakte substantiver.

**Tegnsetting - norske regler (ingen unntak):**
- Tillatt: punktum, komma, kolon, bindestrek
- Bindestrek som tankestrek: " - " (mellomrom-bindestrek-mellomrom)
- **Forbudt: mdash (—)** uansett kontekst
- Forbudt: semikolon, ellipsis (...) som stilgrep

**BI-utdanning i søknadsbrevet - obligatorisk format:**
Programnavnet først, deretter modulene, deretter skolen:
"Executive Master of Management fullføres [når] og består av modulene [Modul1], [Modul2] og [Modul3] ved Handelshøyskolen BI."

Aldri: "[Modulnavn] ved Executive Master of Management (Handelshøyskolen BI)"
Aldri: karakterer eller grades
Aldri: "det tredje kurset i rekken" eller tilsvarende nummerering

**Forbudte ord og uttrykk:**
- "lidenskap", "brenner for", "motiveres av", "genuint"
- "jeg søker herved", "jeg er svært interessert"
- "drømmejobb"
- "jeg vil lykkes fordi"
- "direkte overførbar" (AI-floskel)
- "det er en kombinasjon som sjelden finnes" (AI-floskel)

**Tillatte ord AI-en vanligvis unngår:**
- "spennende" (når det er ekte)
- "mersmak" (narrativt bindeledd)
- "for øvrig" (uformelt bindeledd)
- "hull i kompetansen min" (ærlig gap-erkjennelse)

---

## STEG 6: KVALITETSSJEKK

Kjør følgende sjekkliste før output leveres. Alle punkter må bestås:

**Søknadsbrev:**
- [ ] Forteller en sammenhengende historie med retning (erfaring -> innsikt -> utdanning -> denne stillingen)
- [ ] Åpner med arbeidsgivers behov koblet til "min kjernekompetanse"
- [ ] Sier eksplisitt hvorfor kandidaten søker denne stillingen
- [ ] Bruker eksakt språk fra annonsen naturlig integrert i teksten
- [ ] Inneholder ikke mdash (—) - søk aktivt etter tegnet
- [ ] Inneholder ikke karakterer eller grades
- [ ] BI-utdanning: programnavn først, moduler listet, skole til slutt
- [ ] Brownells-avsnittet er et argument med annonsens egne ord, ikke en CV-liste
- [ ] Vegårshei er aktivert med narrativbro til BI (hvis offentlig sektor-rolle)
- [ ] Inneholder ingen av de forbudte ordene/uttrykkene
- [ ] Er mellom 250 og 280 ord
- [ ] Bruker "jeg" naturlig og bevisst (ikke unngått, ikke overbrukt)
- [ ] Avslutter med rolig, direkte invitasjon til samtale
- [ ] Leser naturlig som noe et menneske skrev - ikke klinisk eller abstrakt
- [ ] Stilling utenfor Arendal/Agder: inneholder setning om flyttevillighet
- [ ] Steg 0 (språkkalibrering) ble gjennomført før generering startet

**Selvtest - les brevet høyt:**
Hvis det høres ut som en AI skrev det, skriv det om. Lars sin stemme er varm, direkte og ærlig. Han sier "jeg bor i Arendal" - ikke "kandidaten er lokalt forankret". Han sier "tette hull i kompetansen min" - ikke "adressere kompetansegap".

**CV:**
- [ ] Kjernekompetanser matcher annonsens nøkkelord
- [ ] BI-moduler er korrekt navngitt uten karakterer
- [ ] Profil-ingress er employer-first og rollepresist
- [ ] Maks 2 sider
- [ ] Vegårshei er med (hvis offentlig sektor primærkontekst)

---

## OUTPUT-FORMAT

**Steg 1-3** produserer intern analyse (ikke i leveransen til brukeren, men lagres i `07_application_pack.json`).

**Steg 4** produserer: Spisset CV i markdown-format.

**Steg 5** produserer: Søknadsbrev-tekst klar for kopiering, uten formatering utover avsnittsinndelinger.

**Steg 6** produserer: Godkjent/ikke godkjent med liste over hva som eventuelt må fikses.

**Filstruktur output:**
```
out_runs/<run_id>/<job_id>/
  07_application_pack.json     {analyse, cv_markdown, cover_letter_text, qc_result}
```

---

## VIKTIGE FAKTA OM KANDIDATEN (ikke fra CV - kontekstkunnskap)

| Faktum | Detalj | Aktiveres når |
|---|---|---|
| Vegårshei kommune | Vikariat, politisk sekretariat og arkiv. To digitaliseringsprosjekter: digitalisering av gammelt byggesaksarkiv og innføring av felles intranett på tvers av DDØ. Ga mersmak for offentlig sektor og var starten på BI-løpet. | Offentlig sektor, kommunale roller |
| Lokal forankring | Bosatt i Arendal, nærmeste familie i området | Stillinger i Arendal/Agder |
| IKT Agder | Kjent samarbeidsstruktur | Agder-kommuner, offentlig sektor i regionen |
| Meddommer | Agder tingrett, 2021-2025 | Lokal forankring - bruk sparsomt |
| BI-pivot | Tre moduler over tre år. Retningen gjort konkret over tid. For å bli bedre på det han kan fra før og tette hull. | Alltid der pivot eller motivasjon er relevant |
| Krysningspunktet | "Organisasjon, teknologi, tjenester og folk" - Lars sitt personlige rammeverk for hva han jobber med | Åpningsavsnitt, der det er naturlig |
| Kognitiv profil | Logisk resonnering Score 9 (topp 2%), GMA 7, innovasjonsevne 84-93. persentil | Gap-håndtering, læringsevne-argument - bruk kun i intern analyse |
| Brownells | 7 år, produkt- og tjenesteansvar | Alltid som portefølje/gevinst-kompetanse |

---

## ENDRINGSLOGG

| Versjon | Dato | Endring |
|---|---|---|
| 1.0 | April 2026 | Initiell versjon. Basert på Sykehuspartner-modellen (depersonalisert). |
| 2.0 | April 2026 | Full revisjon etter kalibrering mot Lars sin endelige Arendal-tekst. Personlig stemme erstatter depersonalisert stil. Narrativ bue som nytt kjernekonsept. Motivasjon sies eksplisitt. BI-format omskrevet. Rekkefølge Brownells->Vegårshei. Ny selvtest. |
| 2.1 | April 2026 | Lagt til Steg 0 (språkkalibrering med refleksjonsspørsmål). Modellkrav (best mulig, lengst tenketid). Flyttevillighet obligatorisk for stillinger utenfor Arendal/Agder. |
