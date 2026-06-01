# Implementation Log — KK2 Input Layer

*Syfte: Dokumentera vad som byggdes och varför, för att senare kunna jämföra mot kravspec och validera att arbetet är korrekt och fullständigt.*

---

## Vad som byggdes

Input-lagret för KK2 (Oraklet) — de två endpoints som tar emot data och exponerar statistik:

- `POST /data/upload` — tar emot en CSV-fil, validerar den, lagrar den i minnet
- `GET /data/stats` — returnerar `df.describe()` från den uppladdade filen som JSON

---

## Filer som ändrades

### `app/data.py`

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

### `app/main.py`

**Vad:** Två endpoints implementerades:

`upload()`:
- Kontrollerar `file.filename` *innan* `await file.read()` — undviker att läsa potentiellt stora filer i onödan om filnamnet saknas
- Läser filinneehållet, skickar till `validate_and_store()`
- Fångar `FileTooLargeError` → 413, `ValueError` → 400
- Returnerar `UploadResponse(rows, columns, dtypes)`

`stats()`:
- Anropar `data.get_stats()`
- Fångar `ValueError` (kastad av `get_dataset()` när inget dataset finns) → 404 med "No dataset loaded"

**Varför så:** Routes är avsiktligt tunna — de gör ingenting utom att ta emot HTTP, delegera till domänlogiken, och mappa undantag till HTTP-statuskoder.

---

### `app/tests/test_endpoints.py`

**Vad:** 5 nya testfunktioner lades till:

| Test | Verifierar |
|---|---|
| `test_upload_empty_file` | 400 när filen är 0 bytes, "empty" i felmeddelandet |
| `test_upload_too_large` | 413 när filen överstiger 10 MB, "10 MB" i felmeddelandet |
| `test_upload_no_data_rows` | 400 när CSV:n bara innehåller en header-rad |
| `test_upload_latin1_csv` | 200 när filen är latin-1-kodad (simulerar PGA Tour-data) |
| `test_stats_after_upload` | 200 från `/data/stats` efter uppladdning; verifierar att JSON-serialisering fungerar via `json.dumps()` |

`test_upload_wrong_extension` fick en detail-assertion tillagd: `assert "Only .csv" in r.json()["detail"]`.

`test_ask_no_dataset` markerades `@pytest.mark.xfail(strict=True)` — endpointen `/ai/ask` är inte implementerad än (returnerar 501), men testet dokumenterar förväntad framtida beteende (ska returnera 400 när inget dataset finns).

---

## Vad som medvetet lämnades utanför scope

- **`/ai/ask`-endpointen** — SmolLLM-integration är nästa fas, inte detta input-lager.
- **`PromptBuilder.invoke()`** — TODO-steg i `chain/steps.py`, var redan rött innan detta arbete. Berör inte input-lagret.
- **Trådsäkerhet** — `_dataset` är en global variabel utan lås. Acceptabelt för en skoluppgift med en worker, men inte produktionsredo.
- **Persistent lagring** — data lagras i minnet per specifikation ("i minnet räcker").

---

## Testresultat efter implementationen

```
app/tests/test_endpoints.py — 9 passed, 1 xfailed
app/tests/test_chain.py — 2 passed, 2 failed (pre-existing TODO-stubs)
```

De 2 kedjetesterna som failar (`test_prompt_builder_contains_question`, `test_prompt_builder_contains_stats`) var röda redan innan detta arbete och rör kod vi aldrig rörde.

---

## Commits (kronologisk ordning)

| SHA | Beskrivning |
|---|---|
| `7825518` | feat: implement validate_and_store and upload endpoint (happy path) |
| `94c68b6` | fix: explicit filename check and typed FileTooLargeError for 413 |
| `7ca2d39` | test: add VG edge-case tests for upload validation |
| `88543e7` | test: add detail assertion to test_upload_wrong_extension |
| `e68b86f` | feat: implement /data/stats with numpy serialization fix |
| `6448155` | style: move import json to module level |
| `877c697` | fix: check filename before reading file body; mark ask test as xfail |

---

## Kravspec-täckning (KK2 Uppgift.md)

| Krav | Status |
|---|---|
| `POST /data/upload` validerar extension | ✅ |
| `POST /data/upload` returnerar rows, columns, dtypes | ✅ |
| `GET /data/stats` returnerar describe() som JSON | ✅ |
| `GET /data/stats` returnerar 404 om inget dataset | ✅ |
| VG: ogiltig CSV (fel extension, tom fil) | ✅ |
| VG: validering av filstorlek | ✅ (10 MB-gräns) |
| VG: encoding-hantering | ✅ (UTF-8 → latin-1 fallback) |
| VG: meningsfulla statuskoder och felmeddelanden | ✅ |
| `POST /ai/ask` | ❌ ej implementerat (nästa fas) |
| Runnable-kedja (PromptBuilder, LLMRunner, ResponseParser) | ❌ stubs kvar (nästa fas) |
