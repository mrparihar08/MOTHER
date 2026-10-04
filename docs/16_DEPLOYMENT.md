# 16 - Deployment & Operational Configuration

The MOTHER backend is optimized for containerized and cloud platform hosting (specifically [Render](https://render.com)).

---

## 1. Render Blueprint (`render.yaml`)

```yaml
version: "1"
services:
  - type: web
    name: MOTHER
    runtime: python
    repo: https://github.com/mrparihar08/MOTHER
    plan: free
    region: oregon
    buildCommand: pip install -r requirements.txt
    startCommand: uvicorn backend.app.app:app --host 0.0.0.0 --port $PORT
    envVars:
      - key: ENVIRONMENT
        value: production
      - key: SECRET_KEY
        generateValue: true
      - key: FRONTEND_URL
        value: https://vitya-chat.onrender.com
      - key: DATABASE_URL
        fromDatabase:
          name: vitya-database
          property: connectionString
```

---

## 2. Startup Entrypoint (`backend/main.py`)

- Adds repository root to `sys.path` to ensure reliable package imports across cloud containers.
- Binds to `0.0.0.0` and reads `$PORT` dynamically from environment variables (defaults to `10000`).

---

## 3. Static Directories & Permissions
On startup, `backend/app/app.py` ensures that `uploads/` and `assets/` exist on disk, mounting them at `/uploads` and `/assets`.