# 12 - Authentication & Security Architecture

The MOTHER backend utilizes a robust stateless JSON Web Token (JWT) authentication system, decoupled from database operations, complemented by refresh tokens, strict password hashing, and CORS origin validation.

---

## 1. Architecture Overview

```text
Frontend (JWT / Secure Cookie)
  ↓
FastAPI Authentication Dependency (token_required / optional_current_user)
  ↓
AuthenticatedUser Principal (Stateless, no DB query)
  ↓
Protected Route Handler
  ↓
Database Session (SQLAlchemy Session - only when DB operations are needed)
  ↓
PostgreSQL / SQLite
```

---

## 2. Token Lifecycle & Algorithms (`backend/api/auth.py`)

- **Algorithm**: `HS256` (HMAC with SHA-256).
- **Access Tokens**:
  - Expiration: **30 Minutes** (Configurable via `ACCESS_TOKEN_EXPIRE_MINUTES`).
  - Payload: `{"user_id": int, "email": str, "username": str, "name": str, "type": "access", "exp": datetime}`.
  - Function: `create_access_token(data: dict | int | AuthenticatedUser)`.
- **Refresh Tokens**:
  - Expiration: **7 Days** (Configurable via `REFRESH_TOKEN_EXPIRE_DAYS`).
  - Payload: `{"user_id": int, "type": "refresh", "exp": datetime}`.
  - Function: `create_refresh_token(data: dict | int | AuthenticatedUser)`, `verify_refresh_token(token: str)`.
  - Stored in HttpOnly, Secure, SameSite cookies for browser clients, with support for request body/Bearer token.
- **Password Reset Tokens**:
  - Expiration: **15 Minutes** (Short-lived security window).
  - Payload: `{"sub": email, "purpose": "password_reset", "exp": datetime}`.
  - Functions: `create_reset_token(email: str)`, `verify_reset_token(token: str)`.
- **Secret Key Security**:
  - Enforces non-default `SECRET_KEY` in `ENVIRONMENT=production`. Raises a runtime exception on startup if default dummy keys (`change-me`, `dev-secret-key`) are detected in production.

---

## 3. Authentication Guards & Dependencies

```python
# Mandatory authentication guard (Throws 401 if missing/invalid/wrong type)
def token_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token_param: Optional[str] = Query(None, alias="token"),
) -> AuthenticatedUser:
    ...

# Optional authentication guard (Returns AuthenticatedUser or None without raising 401)
def optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_optional),
    token_param: Optional[str] = Query(None, alias="token"),
) -> Optional[AuthenticatedUser]:
    ...
```

---

## 4. Password Hashing & Encryption

- **Library**: `passlib[bcrypt]` and `bcrypt`.
- **Context**: `CryptContext(schemes=["bcrypt"], deprecated="auto")`.
- Passwords are salt-hashed before database persistence; raw passwords are never logged or stored.

---

## 5. CORS & Network Security (`backend/app/app.py`)

- **Origin Regex**: Matches all local development environments (`localhost`, `127.0.0.1` with any port) and production Render subdomains:
  ```python
  allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.onrender\.com$"
  ```
- **Credentials Support**: `allow_credentials=True` enabled for secure authorization headers and cookies.