import os
import sys
from pathlib import Path

# Tests always run offline on sample data, with no AI key.
os.environ["DATA_MODE"] = "sample"
os.environ["OPENAI_API_KEY"] = ""
os.environ["FINNHUB_API_KEY"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
