import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

HF_API_KEY: str = os.getenv("HF_API_KEY", "")
PGA_DATA_PATH: str = os.getenv(
    "PGA_DATA_PATH",
    r"C:\Users\lukas\projects\PGA-Tour-Data-Science-Project-master\pgatour_raw_2018_2024.csv",
)
DEMO_SCORECARD_PATH: Path = Path(__file__).parent.parent / "data/demo_scorecard.csv"