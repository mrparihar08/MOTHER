"""
Cryptography, RSA Keys, JWKS, and Password Hashing for Auth Service.
"""
import os
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from passlib.context import CryptContext
import jwt

# Password hashing configuration (Argon2id primary, bcrypt backward-compatible)
pwd_context = CryptContext(
    schemes=["argon2", "bcrypt"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4,
)

# JWT Parameters
JWT_ISSUER = os.getenv("JWT_ISSUER", "https://auth.vitya.ai")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "vitya-services")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))
KEY_ID = os.getenv("JWT_KID", "vitya-auth-key-2026-1")


class RSAKeyManager:
    """Manages the RSA key pair for asymmetric RS256 token signing and JWKS distribution."""

    _instance = None

    def __init__(self):
        self.kid = KEY_ID
        self.private_key = None
        self.public_key = None
        self.public_pem = None
        self._load_or_generate_keys()

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = RSAKeyManager()
        return cls._instance

    def _load_or_generate_keys(self):
        priv_pem_env = os.getenv("RSA_PRIVATE_KEY_PEM")
        if priv_pem_env:
            try:
                self.private_key = serialization.load_pem_private_key(
                    priv_pem_env.encode("utf-8"), password=None
                )
                self.public_key = self.private_key.public_key()
            except Exception:
                self.private_key = None

        if not self.private_key:
            # Generate new 2048-bit RSA key pair
            self.private_key = rsa.generate_private_key(
                public_exponent=65537,
                key_size=2048,
            )
            self.public_key = self.private_key.public_key()

        self.public_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode("utf-8")

    def get_jwks(self) -> Dict[str, Any]:
        """Returns standard JWKS representation containing public key components."""
        jwk_dict = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.public_key))
        jwk_dict["kid"] = self.kid
        jwk_dict["use"] = "sig"
        jwk_dict["alg"] = "RS256"
        jwk_dict["pem"] = self.public_pem
        return {"keys": [jwk_dict]}

    def create_access_token(
        self,
        user_id: int,
        email: str,
        roles: Optional[List[str]] = None,
        permissions: Optional[List[str]] = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        now = datetime.now(timezone.utc)
        if expires_delta:
            expire = now + expires_delta
        else:
            expire = now + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

        payload = {
            "sub": str(user_id),
            "email": email,
            "roles": roles or ["user"],
            "permissions": permissions or [],
            "iss": JWT_ISSUER,
            "aud": JWT_AUDIENCE,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "jti": str(uuid.uuid4()),
        }

        token = jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )
        return token

    def create_refresh_token(self, user_id: int) -> str:
        now = datetime.now(timezone.utc)
        expire = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
        payload = {
            "sub": str(user_id),
            "type": "refresh",
            "iss": JWT_ISSUER,
            "iat": int(now.timestamp()),
            "exp": int(expire.timestamp()),
            "jti": str(uuid.uuid4()),
        }
        return jwt.encode(
            payload,
            self.private_key,
            algorithm="RS256",
            headers={"kid": self.kid},
        )

    def decode_token(self, token: str) -> Dict[str, Any]:
        return jwt.decode(
            token,
            self.public_key,
            algorithms=["RS256"],
            options={"verify_exp": True, "verify_aud": False},
        )


def verify_password(plain_password: str, hashed_password: str) -> bool:
    if not hashed_password or not plain_password:
        return False
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        # Fallback for plain bcrypt if argon2 context parsing encounters edge cases
        import bcrypt
        try:
            return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
        except Exception:
            return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)
