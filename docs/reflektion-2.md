# Projektrapport – KK2 Oraklet

**Lukas Wennström · KK2 · 2026**

---

## Vad projektet är

Oraklet är ett FastAPI för golfcoaching. Användaren laddar upp en CSV med golfrundor; systemet jämför statistiken mot dem bästa spelarna i världens snitt och svarar på frågor om användarens styrkor och svagheter via en lokal språkmodell. Koden är organiserad i tre lager: routes i `app/main.py`, Pandas-hantering och validering i `app/data.py`, och en Runnable-kedja i `app/chain/`.

Projektet startade som ett API med en enkel LLM-kedja, men det överväldigande mesta av arbetet lades på att förstå vad en liten lokal språkmodell har kapacitet till att göra — och att öka modellens precision genom olika experiment till något som faktiskt fungerar. Snarare än att ta in en modell med fler parametrar.

---

## Del 1 — Vad som byggdes

### API:et

Fem endpoints implementerades och fungerar:

- `POST /data/upload` — tar emot en CSV, validerar och lagrar den i minnet
- `GET /data/stats` — returnerar Pandas `describe()` som JSON
- `POST /ai/ask` — kör en fråga genom LLM-kedjan och returnerar ett coachingsvar
- `DELETE /data` — raderar uppladdad data (HTTP 204); uppfyller rätten att bli glömd
- `GET /health` — statuskontroll

Validering i `validate_and_store()` hanterar extension, filstorlek (max 10 MB), radantal (max 1 000 rader), encoding (UTF-8 och latin-1), obligatoriska kolumner och negativa värden. Inkommande frågor saneras i en Pydantic-validator på `AskRequest.question`: whitespace strippas, längden begränsas till 500 tecken, och ett regexmönster avvisar injektionsfraser som "ignore all previous instructions" och "system prompt" (HTTP 422). GDPR-kravet på automatisk rensning hanteras av en TTL-mekanism i `app/data.py`: dataset rensas utan användarinteraktion en timme efter uppladdning. Kedjan `PromptBuilder | LLMRunner | ResponseParser` är sammanlänkad med `|`-operatorn och varje steg har Pydantic-typade in- och utdata.

### Iterationerna på `/ai/ask`-pipelinen (Exp 9)

Det visade sig tidigt att SmolLM2-135M inte klarar att i ett enda anrop identifiera svagaste stat, jämföra mot PGA-snitt och formulera ett konkret råd. Kedjan byggdes om i fyra iterationer:

**Iteration 1** bytte prompten från svenska till engelska. Det löste problemet med nonsens-text och mixade språk, men svaren var generiska — modellen använde sällan de faktiska siffrorna.

**Iteration 2** delade upp kedjan i fem steg: ett Python-steg (`GapAnalyzerStep`) beräknade deterministiskt vilken stat som var sämst, sedan följde fyra smala LLM-anrop — ett för att beskriva svagheten, ett för att föreslå en drill, ett för att koppla till frågan, ett för att sätta ihop svaret. 80% av svaren nämnde nu antingen stats eller drill, men sällan båda.

**Iteration 3** ersatte LLM-steget för drillnamn med en hårdkodad Python-lookup (`_DRILL_DB`). Det tog bort hallucination av drillnamn ("Roller Circles", "GIR Bar") och sänkte svarstiden med 34%. Flaskhalsen var nu tydligt identifierad: det avslutande kompositonssteget.

**Iteration 4** tvingade det avslutande steget att generera JSON med obligatoriska fält via `outlines`-biblioteket och ett Pydantic-schema (`CoachingOutput`). Effekten var dramatisk: 20 av 20 svar innehöll spelarens faktiska siffror, upp från 3 av 20 i iteration 1. JSON-schemat gör det strukturellt omöjligt för modellen att utelämna siffrorna.

**Iteration 5** handlade om att generera ny träningsdata som exakt matcha de prompt-strängar pipelinen faktiskt skickar, och fine-tunea SmolLM2-135M på dem. I experiment 8 framgick det att ~100-300 exempel ger mätbar förbättring; ~500 ger stabil och hög accuracy; medans data endast ger marginel förbättring. Träningen för hög tillförlitlighet estimerades ta ~75h och därför avbröts experimentet 9 här. 
Hade man haft mer tid skulle man eventuellt kunna minska mängden träningsdata och se om fine-tuning kunde hjälpa en liten modell att klara av uppgiften. 

### Slagtypsklassificeraren (Exp 3–8)

Parallellt med `/ai/ask`-arbetet undersöktes en annan tillämpning: att tolka fritt skrivna golfyttranden ("Lågchip mot flaggan, stannade en meter bort") till strukturerade fält (`{"shot_type": "chip"}`). Det är uppgiften där LLM faktiskt tillför något — fri text till struktur — till skillnad från att jämföra siffror, vilket är deterministisk logik.

Sex modeller och metoder testades:

| Metod | Accuracy (svenska) |
|---|---|
| SmolLM2-135M, zero-shot | 20% |
| Supra-50M | 10% |
| Qwen3-0.6B, zero-shot | 24% |
| Qwen3-0.6B, few-shot | 33% |
| Semantisk kod (`SemanticShotClassifier`) | 90% |
| Qwen3-0.6B, fine-tunad LoRA | 65% |

Det viktigaste resultatet: en nyckelordsbaserad klassificerare (`SemanticShotClassifier`) med tre listor för putt, chip och fullslag nådde 90% accuracy utan inferenstid och utan modell — bättre än samtliga LLM-modeller. Fine-tuning av Qwen3-0.6B med LoRA (160 träningsexempel, 30 minuter CPU) gav 65% — den näst bästa metoden.

Slutsatsen som drog: accuracy-taket för 50–600M-modeller på svenska golftext ligger runt 24–44% oavsett modellstorlek. Det är ett domänkunskapsproblem, inte ett storleksproblem. Semantisk kod hanterar 9 av 10 fall deterministiskt; LLM sparas för de genuint tvetydiga fallen.

Viktigt att notera att denna träningen gjordes på svenska. Något som modellerna tydligt inte är anpassade för. En hägre accuracy förväntas om modellerna fått engelska instruktioner.

### Hybridarkitekturen

Arbetet konvergerade mot en tre-nivå-arkitektur:

| Nivå | Komponent | Latens | Molnberoende |
|---|---|---|---|
| 1 | Semantisk kod | ~0 ms | nej |
| 2 | Fine-tunad SmolLM2/Qwen3-LoRA | 2–4 s | nej |
| 3 | API-modell post-runda (Haiku) | ~1 s | ja |

Det är edge AI-mönstret: tung inferens delegeras till moln enbart när precision krävs och latenstolerans är hög. Tunga beräkningar under rundan (på banan) görs lokalt utan nätverksanrop.

### Indexering av reflektionen för AI-läsning

Reflektionsdokumentet växte till 1 162 rader under projektets gång — för stort för att läsas in i ett kontextfönster i sin helhet. Det skapade ett praktiskt problem: varje ny AI-session behövde antingen läsa hela dokumentet (dyrt och långsamt) eller missa relevant kontext.

Lösningen var att bygga ett kompakt index: `docs/reflektion_index.md` är en 60-raderstabelle med sektionsetikett och startrad för varje experiment och sektion. En AI-session läser indexet först, identifierar relevant rad N, och hämtar sedan enbart den sektionen via `Read offset=N limit=80`. Det är RAG-principen utan vektordatabas — indexet är tillräckligt strukturerat för att radnummerbaserad uppslagning räcker.

Indexets kvalitet testades med en eval-agent (`scripts/run_index_eval.py`) som kör ett tre-stegs flöde: SmolLM2 läser indexet och väljer sektion (navigate), kod extraherar sektionen (retrieve), SmolLM2 svarar på frågan (answer). SmolLM2 valdes medvetet som stresstest — om en 135M-modell kan navigera rätt utan tool use är indexet tillräckligt tydligt för vilken AI-klient som helst.

Kopplingen till hybridarkitekturens princip är direkt: deterministisk kod (radnummeruppslag) hanterar det enkla, och LLM anropas enbart för genuint tvetydiga fall — precis som `SemanticShotClassifier` täcker 90% av yttrandena och modellen aktiveras bara som fallback.

---

## Del 2 — Överlapp med uppgiften

Uppgiften ställer krav inom fem områden: funktionskrav, tekniska krav, tester och reflektion.

### Funktionskrav

Alla fem endpoints är implementerade och fungerar. `/ai/ask` kör frågan genom Runnable-kedjan med mer än tre steg.

### Tekniska krav

Runnable-kedjan med `|`-operatorn är implementerad. Pydantic-modeller används på varje stegs in- och utdata. SmolLM2 körs via `transformers.pipeline`. `.env` är exkluderat från Git. Felhantering finns med meningsfulla HTTP-statuskoder. Säkerhetskraven är uppfyllda: prompt injection-skydd via Pydantic-validator och radgräns på CSV-uppladdning. GDPR-kraven täcks av `DELETE /data` och automatisk TTL-rensning.

### Tester

Testerna i `app/tests/` täcker endpoints (TestClient), kedjesteg i isolation (PromptBuilder, ResponseParser), och `/ai/ask` med mockad LLMRunner. Edge cases täcks: LLM-exception → 500, tomt modellsvar, negativa CSV-värden, CSV med för många rader, SemanticShotClassifier (15 parametriserade fall), HybridShotClassifier. Säkerhets- och GDPR-testerna verifierar att injektionsfraser avvisas (HTTP 422), att `DELETE /data` rensar datasetet, att idempotent radering fungerar, och att TTL-mekanismen triggar korrekt via `monkeypatch`.

### Reflektion

Uppgiften ber om en reflektion på 1–2 A4-sidor som täcker fyra sektioner. Den ursprungliga `reflektion.md` är 1 162 rader och täcker nio experiment, arkitekturval, och lärdomar om edge AI. Innehållet täcker uppgiftens fyra sektioner men är inbäddat i ett mycket större material som uppgiften inte bad om.

### Vad som gjordes men inte efterfrågades

Det mesta av projektets faktiska arbete — slagtypsklassificeraren, sex modellers komparativa evaluering, LoRA fine-tuning, constrained decoding med Outlines, hybridarkitekturen, iterationsserien på `/ai/ask` — finns inte i uppgiftens kravlista. Uppgiften bad om en fungerande kedja med SmolLM2. Det som gjordes var att systematiskt kartlägga var SmolLM2 faktiskt fungerar, var den misslyckas, och hur man kompenserar för det — antingen med deterministisk kod, fine-tuning, eller strukturerade output-constraints.

