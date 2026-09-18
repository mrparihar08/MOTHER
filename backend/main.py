import os
import sys
from pathlib import Path
import uvicorn

# Ensure repository root is on sys.path so 'backend' package imports resolve
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))



def start():
    port = int(os.environ.get("PORT", 10000))  # Use Render port if available

    uvicorn.run(
        "backend.app.app:app",
        host="0.0.0.0",
        port=port,
    )


if __name__ == "__main__":
    start()