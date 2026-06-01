# KK2 – Oraklet: en typad LLM-kedja med FastAPI och SmolLLM

## Vad KK2 är

KK2 är den andra och sista kunskapskontrollen. Där KK1 handlade om att *utforska och visualisera* data, handlar KK2 om att *bygga en tjänst* som kombinerar dataanalys med AI – och att göra det med **egna, starkt typade abstraktioner**.

Du ska bygga ett REST-API i FastAPI som:

- Tar emot ett dataset (CSV), analyserar det med Pandas
- Låter användaren ställa naturliga frågor om datat
- Använder en **SmolLLM**-modell från HuggingFace för att generera svar
- Orkestrerar hela flödet genom **din egen Runnable-kedja** – samma mönster som i `design-pattern/llm/llm.py`

Du bygger vidare på exakt det vi gjorde på lektionen: en typad kedja där varje steg är en `Runnable[Input, Output]`, sammanlänkade med `|`-operatorn. Skillnaden är att ett av stegen nu är en **riktig språkmodell** – inte en simulerad sådan.

---

## Vad du ska bygga

### Funktionskrav

Din FastAPI-applikation ska ha minst dessa endpoints:

#### `POST /data/upload`

Accepterar en CSV-fil via form-data (`UploadFile`). Validerar att filen har rätt extension och är läsbar. Läser in den med Pandas och returnerar grundläggande metadata:

```json
{
  "rows": 150,
  "columns": ["city", "temp_c", "precip", "sun_h"],
  "dtypes": {"city": "object", "temp_c": "float64", "precip": "int64", "sun_h": "int64"}
}
```

Datasetet sparas temporärt (i minnet räcker) för senare anrop.

#### `GET /data/stats`

Returnerar beskrivande statistik från Pandas `describe()` som JSON. Om inget dataset laddats upp: `404` med ett meningsfullt felmeddelande.

#### `POST /ai/ask`

Hjärtat i applikationen. Tar en fråga:

```json
{
  "question": "Vilken stad har högst medeltemperatur och varför?"
}
```

och returnerar ett svar genererat av SmolLLM:

```json
{
  "question": "Vilken stad har högst medeltemperatur och varför?",
  "answer": "Malmö har högst medeltemperatur med 8.3 °C.",
  "model": "HuggingFaceTB/SmolLM2-135M-Instruct"
}
```

**Viktigt:** bearbetningen från fråga → prompt → modellanrop → svar ska ske genom en **Runnable-kedja** – samma mönster som `ticket_pipeline` i `design-pattern/`. Kedjan ska ha **minst tre steg** där varje steg är en `Runnable` med typade in- och utdata.

#### `GET /health`

```json
{"status": "ok"}
```

### Tekniska krav

1. **Egen Runnable-kedja.** Du ska använda (och vid behov bygga ut) mönstret från `design-pattern/llm/llm.py`:
   - En `Runnable` som bygger prompten (systeminstruktion + statistik + fråga)
   - En `Runnable` som anropar SmolLLM via `transformers.pipeline`
   - En `Runnable` som tolkar modellens råoutput till ett strukturerat svar
   - Kedjan skapas med `|`-operatorn: `prompt_builder | llm_runner | response_parser`

2. **Pydantic genom hela kedjan.** Varje stegs in- och utdata ska vara Pydantic-modeller. Du har sett mönstret: `SentimentAnalyser[TicketInput, dict]`, `TicketParser[dict, ProcessedTicket]`. Gör samma sak här.

3. **SmolLLM via `transformers`.** Använd `transformers.pipeline("text-generation", model="HuggingFaceTB/SmolLM2-135M-Instruct")` – samma paket som i `design-pattern/pyproject.toml`. Du kan köra modellen lokalt (den är liten nog för en laptop) eller via HuggingFace Inference API.

4. **`.env` för känsliga värden.** Om du använder API-nyckel till HuggingFace, läs den via `os.getenv()` med `.env`-fil. `.env` får **inte** checkas in i Git.

5. **Felhantering.** `HTTPException` vid ogiltig indata, saknat dataset, modellfel. Meningsfulla statuskoder och meddelanden.

6. **Projektstruktur.** Separat `app/`-mapp. Koden ska gå att starta med:

   ```bash
   uv sync
   uv run uvicorn app.main:app --reload
   ```

7. **README.md** med installationsinstruktioner, exempelanrop (curl eller Swagger), och eventuella antaganden du gjort.

---

## Testning

Du ska skriva tester för din applikation med `pytest` – samma ramverk du använt sedan dag ett. Testerna ska täcka **minst tre olika aspekter** av din applikation. Förslag på vad du kan testa:

- **Kedjesteg i isolation.** Varje `Runnable`-steg går att testa separat. Skriv ett test per steg: ge det känd indata och verifiera att utdatan är korrekt. Exempel: `PromptBuilder` får en `PromptBuilderInput` med en känd fråga och statistik – verifiera att prompten innehåller rätt delar.
- **Endpoints.** Använd FastAPI:s `TestClient` (samma mönster som i De spridda vakterna) för att testa att dina endpoints returnerar rätt statuskoder och att svaren har rätt struktur. Exempel: `POST /data/upload` med en giltig CSV ger `200`, med en ogiltig fil ger `400`, `GET /data/stats` utan uppladdat dataset ger `404`.
- **Mockad modell.** För att testa `/ai/ask`-flödet tillförlitligt utan att anropa den riktiga modellen: mocka `LLMRunner.invoke()` med `pytest.monkeypatch` eller `unittest.mock` så att den returnerar ett fördefinierat svar. Då kan du snabbt och repeterbart verifiera hela kedjan.

Testerna ska gå att köra med:

```bash
uv run pytest app/tests/ -v
```

---

Strukturförslag:

```
app/
├── tests/
│   ├── __init__.py
│   ├── test_endpoints.py   # TestClient mot dina routes
│   └── test_chain.py       # Tester för dina Runnable-steg
```

**Placering i G/VG-kraven:** Tester är ett krav för G – minst tre tester som täcker olika aspekter. För VG: testa även edge cases (vad händer om modellen kastar ett undantag? Vad händer med en CSV som har konstiga kolumnnamn?).

## Reflektionsrapport

En markdown (.md) fil (1–2 A4-sidor) som täcker följande punkter. Använd gärna konkreta exempel från din egen kod.

### 1. Säkerhetsaspekter

- Hur skyddar du API-nycklar? Vad hade hänt om `.env` checkats in i Git?
- Vilka risker finns med att ta emot godtyckliga filuppladdningar? Hur har du hanterat dem?
- **Prompt injection:** kan en användare få modellen att göra något den inte ska genom att formulera frågan på ett visst sätt? Ge ett konkret exempel på en injection och hur du skulle kunna mitigra den.

### 2. Dataskydd (GDPR)

- Anta att dataseten som laddas upp kan innehålla personuppgifter. Vilka problem innebär det för din tjänst så som den är utformad nu?
- Vad skulle krävas om tjänsten skulle sättas i produktion?

### 3. AI-risker och ansvar

- Vilka begränsningar har en liten modell som SmolLLM jämfört med större modeller? Hur påverkar det kvaliteten på svaren?
- Ge ett konkret exempel på **bias** (partiskhet) som skulle kunna uppstå.
- Hur skulle du testa att din kedja är tillförlitlig? (Tips: `pytest` – du kan mocka modellen.)

### 4. Designval

- Varför är `Runnable`-mönstret med `|`-operatorn kraftfullt? Jämför med att skriva all logik i en enda funktion.
- Vad var det största tekniska hindret och hur löste du det?

---

## Inlämning

1. **Ett publikt GitHub-repo** som innehåller:
   - `app/` – din FastAPI-applikation (med din Runnable-kedja)
   - `pyproject.toml` – alla beroenden
   - `README.md`
   - `reflektion.md`
   - `.gitignore` (exkludera `.env`, `__pycache__`, `.venv`)

2. **Mejla länken** till kursledaren med ämnesraden:

   > `KK2 Malmö – Förnamn Efternamn`

Jag granskar ditt repo och ger skriftlig återkoppling.

---

## Bedömningskriterier

### Godkänt (G)

För godkänt KK2 ska din inlämning:

- Applikationen uppfyller funktionskraven (alla fyra endpoints).
- En Runnable-kedja med **minst tre steg** används för `/ai/ask`-flödet.
- Kedjans steg har Pydantic-typade in- och utdata.
- SmolLLM är integrerad via `transformers.pipeline`.
- `.env` är inte incheckad i Git.
- Felhantering finns med meningsfulla HTTP-statuskoder.
- Reflektionsrapporten berör alla fyra punkter och visar ett medvetet förhållningssätt.

### Väl godkänt (VG)

För väl godkänt ska du utöver G-kraven visa:

**Robusthet.** Din applikation hanterar edge cases medvetet:

- Ogiltig CSV (fel extension, tom fil, fel encoding)
- Fråga till `/ai/ask` utan att dataset laddats upp → `400`
- Modellen returnerar tomt svar eller tar för lång tid
- Validering av filstorlek (rimlig gräns)

**Kedjedesign.** Din kedja är genomtänkt:

- Prompt-steget formaterar statistiken så att modellen kan resonera kring den
- Systeminstruktionen ramar in modellens roll och språk
- Response-parser-steget extraherar det relevanta ur modellens råoutput – modeller genererar ofta mer än själva svaret. Plocka ut det som är användbart.

**Kodkvalitet.**

- Typannoteringar på funktionssignaturer
- Separation of concerns (routes, schemas, kedja, config i separata filer)
- Loggning av anrop och fel (Pythons `logging`-modul)

**Reflektionen är specifik.** Du ger konkreta exempel från din egen kod när du diskuterar risker. Prompt injection-diskussionen innehåller ett faktiskt injection-försök och en föreslagen mitigring. Du resonerar kring *varför* en åtgärd fungerar, inte bara *att* du vidtagit den.

Du behöver inte uppfylla varje VG-punkt perfekt. Men en inlämning som visar att du tänkt igenom robusthet, promptdesign och risker – och kan artikulera det – är en VG-inlämning.

---

## Starthjälp

### Projektstruktur att utgå från

```
kk2-oraklet/
├── app/
│   ├── __init__.py
│   ├── main.py          # FastAPI-app, endpoints
│   ├── config.py         # .env, settings
│   ├── schemas.py        # Pydantic-modeller för API:t
│   ├── chain/
│   │   ├── __init__.py
│   │   ├── runnable.py   # Runnable, RunnableLambda, RunnableSequence (från llm.py)
│   │   ├── steps.py      # Dina kedjesteg: PromptBuilder, LLMRunner, ResponseParser
│   │   └── pipeline.py   # Den sammansatta kedjan
│   └── data.py           # Pandas-hantering, lagring av dataset
├── pyproject.toml
├── README.md
├── reflektion.md
└── .gitignore
```

### Köra modellen lokalt vs API

- **Lokalt** (rekommenderat): `transformers.pipeline` laddar ner modellen första gången – ca 300 MB för 135M-varianten. Fungerar utan internet efter nedladdning. Något långsammare på CPU men fullt körbart. Ingen API-nyckel behövs.
- **API:** Använd HuggingFace Inference API om du föredrar att inte ladda ner modellen. Kräver API-nyckel och internet. Du kan använda `langchain-huggingface` för detta, men det är inte obligatoriskt.

Båda vägarna är godkända. Att köra lokalt är mer lärorikt och kräver inga externa konton.

---

## Koppling till lektionen Runnable

| Lektionen (Runnable) | KK2 (Oraklet) |
|---|---|
| `Runnable[I, O]` | Samma basklass – du använder den oförändrad |
| `SentimentAnalyser[TicketInput, dict]` | `PromptBuilder[PromptBuilderInput, PromptBuilderOutput]` |
| `TicketParser[dict, ProcessedTicket]` | `ResponseParser[LLMRunnerOutput, ResponseParserOutput]` |
| `ticket_pipeline = Analyser() \| Parser() \| route` | `oraklet = PromptBuilder() \| LLMRunner() \| ResponseParser()` |
| `__or__` / `__ror__` för kedjning | Samma operatorer |
| Simulerad NLP | Riktig NLP via `transformers.pipeline` |
| `TicketInput`, `ProcessedTicket` | Dina egna Pydantic-modeller genom hela flödet |

Ni har redan byggt motorn. KK2 är att sätta den i en riktig bil.

---

## Om du fastnar

Du har byggt kedjor förut – på lektionen. Du har byggt FastAPI-appar – portal-backenden, De spridda vakterna. Du har analyserat data med Pandas – KK1. Alla bitar finns. Det nya är att sätta ihop dem.

Om du kör fast: beskriv problemet exakt, läs felmeddelandet underifrån, sök, fråga. Samma process som alltid. Kom till handledningstillfällena med en konkret fråga – *"Jag försöker skicka `df.describe().to_dict()` till min kedja men får 'dict is not JSON serializable'"* är en bra fråga. *"Hur gör man KK2?"* är inte det. Kom ihåg att du ska kunna redogöra för vad du gjort för att försöka hitta svaret själv också.

---

## Vad du *inte* behöver oroa dig för

**Du behöver inte kunna allt innan du börjar.** Börja med det du kan: få upp en FastAPI-app med `/health`. Lägg till filuppladdning. Koppla in Pandas. Sist: bygg kedjan och integrera SmolLLM. Bygg stegvis.

**Du behöver inte en kraftfull dator.** SmolLM2-135M är designad för att köras på CPU. Den tar några sekunder per anrop – det är helt ok.

**Du behöver inte ett imponerande dataset.** `make_climate()` från Kartografens Verkstad, Palmer Penguins, eller ett enkelt CSV-du hittar själv. Det är integrationen och kedjan som bedöms, inte datan.

**Du behöver inte göra det perfekt.** KK2 är *demonstration av kompetens*, inte *demonstration av perfektion*. En fungerande applikation med en genomtänkt reflektion är det vi söker.

---

## Tre mantran för Oraklet

> *Typning är din kompass.*
> En `Runnable[PromptBuilderInput, PromptBuilderOutput]` berättar exakt vad som går in och vad som kommer ut. Du kan resonera om hela kedjan utan att läsa implementationen av varje steg. Det är poängen.

> *Kedjan är din infrastruktur.*
> Varje steg gör en sak. Stegen är utbytbara. Du kan testa varje steg isolerat med `pytest`. Du kan byta ut SmolLLM mot en annan modell utan att röra resten av koden. Det är friktionen som försvinner – inte komplexiteten.

> *Modellen är en komponent, inte en auktoritet.*
> SmolLLM kan ha fel. Den kan hallucinera. Den kan vara partisk. Din kedja ska behandla modellens output som opålitlig indata till nästa steg – inte som facit.

---

*Kedjan du bygger är samma mönster som driver produktionssystem på riktiga företag. Du har byggt den från scratch. Nu använder du den med en riktig modell. Det är ingen leksak – det är ingenjörskonst.*