# Implementation Log — KK2 (Oraklet)

*Syfte: Dokumentera vad som byggdes och varför, för att kunna jämföra mot kravspec och validera att arbetet är korrekt och fullständigt.*

---

## Session 1 — Input-lagret

### Vad som byggdes

Input-lagret för KK2 (Oraklet) — de två endpoints som tar emot data och exponerar statistik:

- `POST /data/upload` — tar emot en CSV-fil, validerar den, lagrar den i minnet
- `GET /data/stats` — returnerar `df.describe()` från den uppladdade filen som JSON

---

### Filer som ändrades

#### `app/data.py`

**Vad:** Filen fick tre nya komponenter:

1. `FileTooLargeError(ValueError)` — en custom exception-subklass. Används för att skilja "filen är för stor → 413" från alla andra valideringsfel → 400, utan att behöva string-sniffa på felmeddelanden.

2. `validate_and_store(contents: bytes, filename: str) -> pd.DataFrame` — samlar all valideringslogik på ett ställe:
   - Kontrollerar att filnamnet slutar på `.csv`
   - Kontrollerar att filen inte är tom (0 bytes)
   - Kontrollerar att filen inte överstiger 10 MB (kastar `FileTooLargeError`)
   - Försöker avkoda innehållet som UTF-8, faller tillbaka på latin-1 (täcker PGA Tour-datasetet som är latin-1-kodat)
   - Försöker parsa som CSV med pandas
   - Kontrollerar att DataFrame har minst 1 datarad (ej bara header)
   - Sparar via `store_dataset()`

3. `_to_native(v)` + uppdaterad `get_stats()` — löser ett bug där `df.describe().to_dict()` returnerar numpy-typer (`np.float64`, `np.int64`) som Pythons JSON-serialiserare inte klarar. `_to_native` anropar `.item()` på numpy-skalärer för att konvertera till inbyggda Python-typer.

**Varför så:** All valideringslogik i `data.py` gör att `main.py` kan vara tunt (bara HTTP-translation). Det gör logiken testbar isolerat, utan att behöva skicka HTTP-requests.

---

#### `app/main.py`

**Vad:** Två endpoints implementerades:

`upload()`:
- Kontrollerar `file.filename` *innan* `await file.read()` — undviker att läsa potentiellt stora filer i onödan om filnamnet saknas
- Läser filinnehållet, skickar till `validate_and_store()`
- Fångar `FileTooLargeError` → 413, `ValueError` → 400
- Returnerar `UploadResponse(rows, columns, dtypes)`

`stats()`:
- Anropar `data.get_stats()`
- Fångar `ValueError` (kastad av `get_dataset()` när inget dataset finns) → 404 med "No dataset loaded"

**Varför så:** Routes är avsiktligt tunna — de gör ingenting utom att ta emot HTTP, delegera till domänlogiken, och mappa undantag till HTTP-statuskoder.

---

#### `app/tests/test_endpoints.py`

**Vad:** 5 nya testfunktioner lades till:

| Test | Verifierar |
|---|---|
| `test_upload_empty_file` | 400 när filen är 0 bytes, "empty" i felmeddelandet |
| `test_upload_too_large` | 413 när filen överstiger 10 MB, "10 MB" i felmeddelandet |
| `test_upload_no_data_rows` | 400 när CSV:n bara innehåller en header-rad |
| `test_upload_latin1_csv` | 200 när filen är latin-1-kodad (simulerar PGA Tour-data) |
| `test_stats_after_upload` | 200 från `/data/stats` efter uppladdning; verifierar att JSON-serialisering fungerar via `json.dumps()` |

`test_upload_wrong_extension` fick en detail-assertion tillagd: `assert "Only .csv" in r.json()["detail"]`.

`test_ask_no_dataset` markerades `@pytest.mark.xfail(strict=True)` — endpointen `/ai/ask` var inte implementerad än (returnerar 501), men testet dokumenterade förväntad framtida beteende (ska returnera 404 när inget dataset finns).

---

### Vad som medvetet lämnades utanför scope (Session 1)

- **`/ai/ask`-endpointen** — SmolLLM-integration är nästa fas, inte detta input-lager.
- **`PromptBuilder.invoke()`** — TODO-steg i `chain/steps.py`, var redan rött innan detta arbete. Berör inte input-lagret.
- **Trådsäkerhet** — `_dataset` är en global variabel utan lås. Acceptabelt för en skoluppgift med en worker, men inte produktionsredo.
- **Persistent lagring** — data lagras i minnet per specifikation ("i minnet räcker").

---

## Session 2 — Golf Coaching System

### Vad som byggdes

Golf-coaching-lagret ovanpå input-lagret från session 1. Fullständig implementation av `/ai/ask`-endpointen och Runnable-kedjan, samt omdesign av systemet från generisk CSV-analys till ett domänspecifikt golf-coachingsystem.

**Domänbeslut:** Systemet är golf-specifikt. Scorecards (hål-för-hål: par, slag, GIR, putts, fairway) laddas upp via `/data/upload`, jämförs mot PGA Tour-snitt, och systemet bestämmer självt vilka svagheter det ska fråga SmolLLM om. Ingen användarfråga behövs — kedjan orkestrerar hela flödet.

---

### Filer som ändrades

#### `app/config.py`

**Vad:** Lade till `PGA_DATA_PATH` — sökvägen till PGA Tour-datasetet (`pgatour_raw_2018_2024.csv` från det separata scraper-projektet). Läses från env-variabeln `PGA_DATA_PATH` med hardkodad Windows-sökväg som fallback.

**Varför:** Gör sökvägen konfigurerbar utan kodändring inför deploy på Render.

---

#### `app/data.py`

**Vad:** Tre tillägg utöver det befintliga input-lagret:

1. **Scorecard-validering** i `validate_and_store()`:
   - Kontrollerar att obligatoriska kolumner finns (`hole`, `par`, `strokes`, `gir`, `putts`)
   - Kontrollerar att inga negativa värden finns
   - Beräknar och lagrar user stats via `_compute_user_stats()`

2. **`_compute_user_stats(df)`** — beräknar fyra nyckelmetriker från scorecarden:
   - `gir_pct`: andel hål med green in regulation (%)
   - `fairway_pct`: andel par-4/5-hål med fairway träffad (%) — `None` om `fairway_hit` saknas
   - `avg_putts`: genomsnittliga putts per hål
   - `scoring_avg`: genomsnittliga slag per hål

3. **PGA Tour-benchmarks** — `load_pga_benchmarks()` läser `pgatour_raw_2018_2024.csv`, beräknar medelvärden för `GIR_%`, `FWY_%` och `SCORING`. `avg_putts` är en känd konstant (1.73) eftersom den inte finns i CSV:n. Om filen saknas används fallback-konstanter.

4. **`_user_stats`-state** — analogt med `_dataset`: `store_user_stats()`, `get_user_stats()`, rensas av `clear_dataset()`.

**Varför:** `clear_dataset()` nollställer även `_user_stats` så att testerna inte läcker state mellan körningar.

---

#### `app/schemas.py`

**Vad:** Tog bort `AskRequest` och `question`-fältet från `AskResponse`.

**Varför:** `/ai/ask` tar ingen request body — systemet bestämmer frågorna självt baserat på scorecarden. `question` i svaret gav inget värde när det inte finns en användarfråga att echoa tillbaka.

---

#### `app/chain/steps.py`

**Vad:** Komplett omskrivning från 3 stub-steg till 5 implementerade steg med nya Pydantic-modeller.

##### Nya Pydantic-modeller

| Modell | Fält |
|--------|------|
| `WeakArea` | `category`, `user_value`, `pga_avg`, `gap_pct` |
| `StatAnalyserInput` | `user_stats: dict`, `pga_benchmarks: dict` |
| `AnalysisOutput` | `weaknesses: list[WeakArea]`, `user_stats`, `pga_benchmarks` |
| `QuestionsOutput` | `questions: list[str]`, `weaknesses`, `user_stats`, `pga_benchmarks` |
| `PromptBuilderOutput` | `prompt: str` |
| `LLMRunnerOutput` | `raw_text: str` |
| `ResponseParserOutput` | `answer: str` |

##### `StatAnalyser`

Jämför user stats mot PGA Tour-snitt för fyra kategorier och rankar dem efter gap i procent:

- **approach** (GIR): `gap = (pga - user) / pga * 100` — högre gap = sämre än PGA
- **driving** (fairway): samma formel
- **putting** (avg putts): `gap = (user - pga) / pga * 100` — lägre putts är bättre
- **scoring**: `gap = (user_diff - pga_diff) / par_baseline * 100` — normaliserat mot par (4.0) för att undvika att nära-noll pga_diff blåser upp gap-värdet

Returnerar top 3 svagheter sorterade fallande på gap_pct.

##### `QuestionGenerator`

Mappar varje svag kategori till en fördefinierad coaching-fråga på svenska. Statisk mappning — ingen LLM inblandad i detta steg.

##### `PromptBuilder`

Bygger en strukturerad prompt med:
- Systeminstruktion (roll: svensk golfcoach)
- Spelarens stats vs PGA Tour-snitt för alla fyra kategorier
- Identifierade förbättringsområden (från StatAnalyser)
- Numrerade coaching-frågor (från QuestionGenerator)

##### `LLMRunner`

Lazy-laddar `transformers.pipeline("text-generation", model="HuggingFaceTB/SmolLM2-135M-Instruct", max_new_tokens=300)` vid första anrop. Omsluter pipeline-anropet i try/except och loggar fel.

##### `ResponseParser`

Söker efter prompt-ekot i råsvaret (LLMs ekar ofta prompten). Letar efter markören `"Svara kortfattat på följande frågor:"` eller `"1."` och returnerar allt efter. Fallback: returnerar hela texten stripped.

---

#### `app/chain/pipeline.py`

**Vad:** Uppdaterades från 3-stegs till 5-stegs kedja:

```python
oraklet = StatAnalyser() | QuestionGenerator() | PromptBuilder() | LLMRunner() | ResponseParser()
```

---

#### `app/main.py`

**Vad:** Tre ändringar:

1. **Lifespan-event** — `load_pga_benchmarks()` körs vid startup så att PGA-data är redo innan det första request kommer.

2. **`upload()`** — lade till scorecard-kolumnvalidering (delegeras till `data.validate_and_store()`).

3. **`ask()`** — implementerad: hämtar `get_user_stats()` → 404 om inget dataset, hämtar `get_pga_benchmarks()`, bygger `StatAnalyserInput`, anropar `oraklet.invoke()`, returnerar `AskResponse(answer, model)`. Tar ingen request body.

---

#### `app/tests/test_chain.py`

**Vad:** Komplett omskrivning för att matcha den nya 5-stegskedjan.

| Test | Verifierar |
|------|-----------|
| `test_stat_analyser_identifies_weakest_area` | GIR-gap (≈48%) rankas högre än scoring-gap (≈39%) för typisk amatör |
| `test_stat_analyser_returns_at_most_three_weaknesses` | Kedjan returnerar max 3 svagheter |
| `test_question_generator_maps_categories` | Rätt frågor genereras för approach och putting |
| `test_prompt_builder_contains_stats` | Prompt innehåller user stats och PGA-snitt |
| `test_response_parser_strips_prompt_echo` | Parser hittar svaret efter prompt-markören |
| `test_full_chain_with_mocked_llm` | Hela kedjan från `StatAnalyserInput` till `ResponseParserOutput` med mockad LLMRunner |

---

#### `app/tests/test_endpoints.py`

**Vad:** Uppdaterade befintliga tester och lade till nya.

- `VALID_SCORECARD` — en 18-håls konstant i rätt scorecard-format, används i flera tester
- `test_upload_valid_scorecard` — ersätter generisk CSV med scorecard-format
- `test_upload_missing_scorecard_columns` — ny: 400 när obligatoriska scorecard-kolumner saknas
- `test_ask_no_dataset` — ny: 404 (ej 400) när inget dataset finns vid ask
- `test_ask_returns_answer` — ny: komplett ask-flöde med mockad LLMRunner

---

### Designbeslut (Session 2)

**Varför 5 steg istället för 3?** Uppgiften kräver minst 3, men `StatAnalyser` och `QuestionGenerator` är genuint separata ansvar: ett analyserar data, ett genererar frågor baserat på analysen. Att slå ihop dem till ett steg hade gjort steget svårare att testa och ändra isolerat.

**Varför bestämmer systemet frågorna?** SmolLM2-135M är för liten för att göra pålitlig statistisk analys. Python ansvarar för det faktabaserade (vilka stats är sämst), LLM ansvarar för coaching-kunskapen (konkreta råd för just de svaga områdena). Modellen är en komponent, inte en auktoritet.

**Varför normaliseras scoring-gap mot par och inte mot pga_diff?** PGA Tour-snittet per hål (≈3.92) är nära par (4.0), vilket ger ett pga_diff nära noll. Division med ett nära-noll-värde blåste upp scoring-gapet artificiellt (>1000%) och dominerade rankningen felaktigt. Normalisering mot par ger ett tolkningsbart och rättvist värde.

---

## Commits (kronologisk ordning)

*Session 1-commits (med SHA):*

| SHA | Beskrivning |
|---|---|
| `7825518` | feat: implement validate_and_store and upload endpoint (happy path) |
| `94c68b6` | fix: explicit filename check and typed FileTooLargeError for 413 |
| `7ca2d39` | test: add VG edge-case tests for upload validation |
| `88543e7` | test: add detail assertion to test_upload_wrong_extension |
| `e68b86f` | feat: implement /data/stats with numpy serialization fix |
| `6448155` | style: move import json to module level |
| `877c697` | fix: check filename before reading file body; mark ask test as xfail |

*Session 2-commits saknar SHA:er i loggen.*

---

## Testresultat (slutläge)

```
app/tests/test_chain.py     — 6 passed
app/tests/test_endpoints.py — 12 passed
Totalt: 18 passed, 0 failed
```

---

## Kravspec-täckning (KK2 Uppgift.md)

| Krav | Status |
|------|--------|
| `POST /data/upload` validerar extension | ✅ (Session 1) |
| `POST /data/upload` returnerar rows, columns, dtypes | ✅ (Session 1) |
| `GET /data/stats` returnerar describe() som JSON | ✅ (Session 1) |
| `GET /data/stats` returnerar 404 om inget dataset | ✅ (Session 1) |
| VG: ogiltig CSV (fel extension, tom fil, saknade kolumner) | ✅ |
| VG: validering av filstorlek | ✅ (10 MB-gräns) |
| VG: encoding-hantering | ✅ (UTF-8 → latin-1 fallback) |
| VG: meningsfulla statuskoder och felmeddelanden | ✅ |
| `POST /ai/ask` returnerar svar från SmolLLM | ✅ (Session 2) |
| `GET /health` | ✅ |
| Runnable-kedja med minst 3 steg | ✅ (5 steg) |
| Pydantic-typade in/utdata per steg | ✅ |
| SmolLLM via `transformers.pipeline` | ✅ |
| VG: response parser strippar prompt-eko | ✅ |
| VG: systeminstruktion ramar in modellens roll | ✅ |
| VG: logging av anrop och fel | ✅ |
| Reflektionsrapport | ❌ ej påbörjad |
