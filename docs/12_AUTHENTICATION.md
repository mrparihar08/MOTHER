# 12 - Authentication & Security Architecture

The MOTHER backend utilizes a robust stateless JSON Web Token (JWT) authentication system, complemented by strict password hashing and CORS origin validation.

---

## 1. Token Lifecycle & Algorithms (`backend/api/auth.py`)

- **Algorithm**: `HS256` (HMAC with SHA-256).
- **Access Tokens**:
  - Expiration: **24 Hours**.
  - Payload: `{"user_id": int, "exp": datetime}`.
  - Function: `create_access_token(data: dict | int)`.
- **Password Reset Tokens**:
  - Expiration: **15 Minutes** (Short-lived security window).
  - Payload: `{"sub": email, "purpose": "password_reset", "exp": datetime}`.
  - Functions: `create_reset_token(email: str)`, `verify_reset_token(token: str)`.
- **Secret Key Security**:
  - Enforces non-default `SECRET_KEY` in `ENVIRONMENT=production`. Raises a runtime exception on startup if default dummy keys (`change-me`, `dev-secret-key`) are detected in production.

---

## 2. Authentication Guards & Dependencies

```python
# Mandatory authentication guard (Throws 401 if missing/invalid)
def token_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    token_param: Optional[str] = Query(None, alias="token"),
    db: Session = Depends(get_db)
) -> User:
    ...

# Optional authentication guard (Returns User object or None without raising 401)
def optional_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security_optional),
    db: Session = Depends(get_db)
) -> User | None:
    ...
```

---

## 3. Password Hashing & Encryption

- **Library**: `passlib[bcrypt]` and `bcrypt`.
- **Context**: `CryptContext(schemes=["bcrypt"], deprecated="auto")`.
- Passwords are salt-hashed before database persistence; raw passwords are never logged or stored.

---

## 4. CORS & Network Security (`backend/app/app.py`)

- **Origin Regex**: Matches all local development environments (`localhost`, `127.0.0.1` with any port) and production Render subdomains:
  ```python
  allow_origin_regex = r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://.*\.onrender\.com$"
  ```
- **Credentials Support**: `allow_credentials=True` enabled for secure authorization headers.