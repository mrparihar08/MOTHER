import os
import uvicorn

def start():
    port = int(os.environ.get("PORT", 10000))  # ✅ use Render port

    uvicorn.run(
        "app.app:app",
        host="0.0.0.0",
        port=port
    )

if __name__ == "__main__":
    start()