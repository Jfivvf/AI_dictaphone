import os

STORAGE_DIR = os.environ.get("AXAI_STORAGE") or os.path.expanduser("~/AxAI_Storage")
MODELS_DIR = os.path.join(STORAGE_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)
