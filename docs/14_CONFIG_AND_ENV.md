# 14 - Configuration & Environment Variables

This document catalogs all environment variables used by the MOTHER backend application.

---

## 1. Environment Variable Reference

| Variable Name | Required? | Default Value | Usage & Impact |
| :--- | :---: | :--- | :--- |
| `ENVIRONMENT` | No | `"development"` | Controls strict production checks (e.g. SECRET_KEY enforcement). |
| `SECRET_KEY` | **Yes (Prod)** | `"dev-secret-key"` | Cryptographic key for signing JWT tokens. |
| `JWT_SECRET_KEY` | No | None | Alternative fallback key for JWT signing. |
| `DATABASE_URL` | No | `"sqlite:///./instance/app.db"` | Primary PostgreSQL / SQLite database connection string. |
| `SUPABASE_DATABASE_URL`| No | None | Supabase-specific PostgreSQL connection string. |
| `SUPABASE_URL` | No | None | Supabase API URL for object storage access. |
| `SUPABASE_KEY` | No | None | Supabase Service / Anon API key. |
| `GEMINI_API_KEY` | **Yes (AI)** | None | Google Generative AI API Key for LLM planning & chat. |
| `GOOGLE_API_KEY` | No | None | Alternate Google API Key variable name. |
| `UNSPLASH_ACCESS_KEY`| No | None | Unsplash Developer API Client ID for photo search. |
| `OPENVERSE_CLIENT_ID`| No | None | Openverse API OAuth Client ID. |
| `OPENVERSE_CLIENT_SECRET`| No| None | Openverse API OAuth Client Secret. |
| `NEWS_API_KEY` | No | None | NewsAPI developer key. |
| `MEDIASTACK_API_KEY` | No | None | Mediastack news developer key. |
| `CURRENTS_API_KEY` | No | None | Currents news developer key. |
| `OPENWEATHER_API_KEY`| No | None | OpenWeatherMap API key for live weather data. |
| `CORS_ORIGINS` | No | Comma-separated defaults | Explicit CORS origin whitelist override. |
| `PORT` | No | `10000` | Port for Uvicorn web server in production (Render). |