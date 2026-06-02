import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, UploadFile, HTTPException
from app.schemas import UploadResponse, AskRequest, AskResponse, HealthResponse, AnalyzeResponse
from app.chain.steps import PromptBuilderInput, AnalyzeState, AskCoTState
from app.chain.pipeline import oraklet, analyse_kedjan, ask_cot_kedjan, preload, CHAT_LORA_PATH
import app.data as data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_lora_cfg = Path(CHAT_LORA_PATH) / "adapter_config.json"
if _lora_cfg.exists():
    MODEL_NAME = json.loads(_lora_cfg.read_text()).get(
        "base_model_name_or_path", "HuggingFaceTB/SmolLM2-135M-Instruct"
    )
else:
    MODEL_NAME = "HuggingFaceTB/SmolLM2-135M-Instruct"


@asynccontextmanager
async def lifespan(app: FastAPI):
    data.load_pga_benchmarks()
    preload()
    yield


app = FastAPI(title="Oraklet", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


@app.post("/data/upload/demo", response_model=UploadResponse, summary="Ladda demo-scorecard")
def upload_demo() -> UploadResponse:
    from app.config import DEMO_SCORECARD_PATH
    if not DEMO_SCORECARD_PATH.exists():
        raise HTTPException(status_code=404, detail="demo_scorecard.csv hittades inte")
    contents = DEMO_SCORECARD_PATH.read_bytes()
    df = data.validate_and_store(contents, DEMO_SCORECARD_PATH.name)
    return UploadResponse(
        rows=len(df),
        columns=list(df.columns),
        dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
    )


@app.post("/data/upload", response_model=UploadResponse)
async def upload(file: UploadFile) -> UploadResponse:
    logger.info("Upload request: %s", file.filename)
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")
    contents = await file.read()
    try:
        df = data.validate_and_store(contents, file.filename)
    except data.FileTooLargeError as e:
        raise HTTPException(status_code=413, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UploadResponse(
        rows=len(df),
        columns=list(df.columns),
        dtypes={col: str(dtype) for col, dtype in df.dtypes.items()},
    )


@app.get("/data/stats")
def stats(
    par: int | None = None,
    hole: int | None = None,
    course: str | None = None,
    date: str | None = None,
) -> dict:
    logger.info("Stats request — filters: par=%s hole=%s course=%s date=%s", par, hole, course, date)
    try:
        df = data.get_filtered_dataset(par=par, hole=hole, course=course, date=date)
    except ValueError as e:
        status = 404 if "No dataset" in str(e) else 400
        raise HTTPException(status_code=status, detail=str(e))
    user_stats = data._compute_user_stats(df)
    pga = data.get_pga_benchmarks()
    pga_scoring_per_hole = round(pga["scoring_avg"] / 18, 2)

    def gap(player, pga_val):
        if player is None:
            return None
        return round(player - pga_val, 1)

    return {
        "meta": {
            "holes_count": len(df),
            "filters": {"par": par, "hole": hole, "course": course, "date": date},
        },
        "scoring_avg": {"player": user_stats["scoring_avg"], "pga_avg": pga_scoring_per_hole, "gap": gap(user_stats["scoring_avg"], pga_scoring_per_hole)},
        "gir_pct":     {"player": user_stats["gir_pct"],     "pga_avg": round(pga["gir_pct"], 1),     "gap": gap(user_stats["gir_pct"],     pga["gir_pct"])},
        "fairway_pct": {"player": user_stats["fairway_pct"], "pga_avg": round(pga["fairway_pct"], 1), "gap": gap(user_stats["fairway_pct"], pga["fairway_pct"])},
        "avg_putts":   {"player": user_stats["avg_putts"],   "pga_avg": pga["avg_putts"],             "gap": gap(user_stats["avg_putts"],   pga["avg_putts"])},
    }


@app.get("/ai/analyze", response_model=AnalyzeResponse)
def analyze() -> AnalyzeResponse:
    try:
        user_stats = data.get_user_stats()
    except ValueError:
        raise HTTPException(status_code=404, detail="No dataset loaded — upload a scorecard first")
    pga = data.get_pga_benchmarks()
    state = AnalyzeState(user_stats=user_stats, pga_benchmarks=pga)
    try:
        result = analyse_kedjan.invoke(state)
    except Exception as e:
        logger.error("Analyze chain error: %s", e)
        raise HTTPException(status_code=500, detail="Model error — try again")
    return AnalyzeResponse(good=result.good, bad=result.bad, tip=result.tip, model=MODEL_NAME)


@app.post("/ai/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    logger.info("Ask request: %s", req.question)
    try:
        user_stats = data.get_user_stats()
    except ValueError:
        raise HTTPException(status_code=404, detail="No dataset loaded — upload a scorecard first")

    pga_benchmarks = data.get_pga_benchmarks()
    chain_input = PromptBuilderInput(
        question=req.question,
        user_stats=user_stats,
        pga_benchmarks=pga_benchmarks,
    )

    cot_input = AskCoTState(
        question=req.question,
        user_stats=user_stats,
        pga_benchmarks=pga_benchmarks,
    )
    try:
        result = ask_cot_kedjan.invoke(cot_input)
    except Exception as e:
        logger.error("Chain error: %s", e)
        raise HTTPException(status_code=500, detail="Model error — try again")

    return AskResponse(question=req.question, answer=result.answer, model=MODEL_NAME)
