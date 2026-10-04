# 15 - Dependency & Library Justification

The MOTHER backend dependencies are pinned in `requirements.txt`.

---

## 1. Core Framework & Web
- `fastapi`: High-performance ASGI web framework.
- `uvicorn[standard]`: Lightning-fast ASGI web server implementation.
- `starlette`: Core ASGI toolkit powering FastAPI.
- `pydantic`: Data validation and settings management using Python type hints.

## 2. Security & Authentication
- `python-jose[cryptography]`: JWT token generation, encoding, and validation.
- `passlib[bcrypt]`, `bcrypt`: Secure password salt-hashing.
- `cryptography`: Low-level cryptographic primitives.
- `email-validator`: Validates email strings in Pydantic schemas.

## 3. Artificial Intelligence & NLP
- `google-generativeai`, `google-genai`: Official Google Gemini SDK for conversational intelligence.
- `tenacity`: Retry decorator with exponential backoff for AI rate limits.
- `wikipedia`: Encyclopedic knowledge extraction.
- `nltk`: Natural Language Toolkit for sentence tokenization and text processing.

## 4. Machine Learning & Data Science
- `scikit-learn`: Powers DORA disease classification and linear expense forecasting.
- `numpy`, `pandas`: Vectorized data manipulation, CSV parsing, and statistical aggregations.
- `scipy`, `joblib`: Model serialization and statistical optimization.

## 5. Document & Presentation Generation
- `python-pptx`: Native Microsoft PowerPoint `.pptx` creation and manipulation.
- `python-docx`: Microsoft Word `.docx` report generation.
- `reportlab`: PDF document compilation.
- `matplotlib`, `seaborn`: High-resolution financial chart generation.

## 6. Image & Multimedia
- `pillow`: Image processing, aspect ratio resizing, and color space transformation.
- `qrcode[pil]`, `python-barcode`: On-the-fly QR code and barcode rendering.
- `opencv-python-headless`: Computer vision utilities for image enhancement.
- `edge-tts`: Microsoft Edge text-to-speech engine for slide voiceovers.

## 7. Database & Storage
- `SQLAlchemy`: Object Relational Mapper for PostgreSQL and SQLite.
- `psycopg2-binary`, `psycopg[binary]`: PostgreSQL database adapters.
- `supabase`: Client library for Supabase storage and services.