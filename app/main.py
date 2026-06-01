import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, UploadFile, HTTPException
from app.schemas import UploadResponse, AskRequest, AskResponse, HealthResponse
from app.chain.steps import PromptBuilderInput
from app.chain.pipeline import oraklet
import app.data as data

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

MODEL_NAME = "HuggingFaceTB/SmolLM2-135M-Instruct"


@asynccontextmanager
async def lifespan(app: FastAPI):
    data.load_pga_benchmarks()
    yield


app = FastAPI(title="Oraklet", lifespan=lifespan)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(status="ok")


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
def stats() -> dict:
    logger.info("Stats request")
    try:
        return data.get_stats()
    except ValueError:
        raise HTTPException(status_code=404, detail="No dataset loaded — upload a scorecard first")


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

    try:
        result = oraklet.invoke(chain_input)
    except Exception as e:
        logger.error("Chain error: %s", e)
        raise HTTPException(status_code=500, detail="Model error — try again")

    return AskResponse(question=req.question, answer=result.answer, model=MODEL_NAME)
