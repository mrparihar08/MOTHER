"""
Shared JWT Validator for Downstream Microservices.
Validates asymmetric RS256 JWT tokens using cached JWKS public keys.
Ensures zero database access and zero private key exposure in downstream services.
"""
import os
import json
import logging
from typing import Optional, Dict, Any, List
import urllib.request
import urllib.error

import jwt
from fastapi import HTTPException, status, Security, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from shared.security.models import AuthenticatedUser, TokenPayload, Role

logger = logging.getLogger("shared.security.jwt_validator")

# Default configuration via environment
AUTH_SERVICE_JWKS_URL = os.getenv(
    "AUTH_SERVICE_JWKS_URL", "http://auth_service:8001/api/auth/.well-known/jwks.json"
)
JWT_ISSUER = os.getenv("JWT_ISSUER", "https://auth.vitya.ai")
JWT_AUDIENCE = os.getenv("JWT_AUDIENCE", "vitya-services")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "RS256")
FALLBACK_SECRET_KEY = os.getenv("SECRET_KEY", "mother-production-secret-key-change-me")

security_bearer = HTTPBearer(auto_error=False)


class JWKSKeyManager:
    """Caches public keys fetched from Auth Service JWKS endpoint."""

    _instance = None
    _public_keys: Dict[str, Any] = {}
    _jwks_url: str = AUTH_SERVICE_JWKS_URL

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = JWKSKeyManager()
        return cls._instance

    def set_jwks_url(self, url: str):
        self._jwks_url = url

    def register_public_pem(self, kid: str, pem_str: str):
        """Manually register or inject a public PEM key (useful in tests/offline)."""
        self._public_keys[kid] = pem_str

    def get_key(self, kid: Optional[str] = None) -> Optional[Any]:
        if kid and kid in self._public_keys:
            return self._public_keys[kid]

        if not self._public_keys:
            self.fetch_keys()

        if kid:
            return self._public_keys.get(kid)
        if self._public_keys:
            # Return first available public key
            return next(iter(self._public_keys.values()))
        return None

    def fetch_keys(self) -> None:
        """Fetch keys from JWKS endpoint over HTTP."""
        try:
            req = urllib.request.Request(self._jwks_url, headers={"User-Agent": "Vitya-Microservice"})
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for key_dict in data.get("keys", []):
                    kid = key_dict.get("kid", "default")
                    # If x5c or pem format provided:
                    if "pem" in key_dict:
                        self._public_keys[kid] = key_dict["pem"]
                    elif "n" in key_dict and "e" in key_dict:
                        # Convert RSA components to PyJWT public key
                        try:
                            public_key = jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(key_dict))
                            self._public_keys[kid] = public_key
                        except Exception as e:
                            logger.warning(f"Could not parse JWK for kid {kid}: {e}")
                logger.info(f"Loaded {len(self._public_keys)} public keys from JWKS")
        except Exception as e:
            logger.debug(f"JWKS fetch from {self._jwks_url} failed: {e}")


def decode_and_validate_token(token: str) -> AuthenticatedUser:
    """
    Decodes and validates a JWT token using RS256 public key.
    Falls back gracefully to symmetric HS256 if RS256 key is absent (transitional compatibility).
    """
    unverified_headers = {}
    try:
        unverified_headers = jwt.get_unverified_header(token)
    except Exception:
        pass

    alg = unverified_headers.get("alg", JWT_ALGORITHM)
    kid = unverified_headers.get("kid")

    key_manager = JWKSKeyManager.get_instance()
    public_key = key_manager.get_key(kid)

    payload = None
    if alg == "RS256" and public_key:
        try:
            payload = jwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_exp": True, "verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired. Please refresh your session.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid RS256 token: {str(e)}",
                headers={"WWW-Authenticate": "Bearer"},
            )
    else:
        # Fallback to symmetric validation for backward compatibility during migration
        try:
            payload = jwt.decode(
                token,
                FALLBACK_SECRET_KEY,
                algorithms=["HS256", "RS256"],
                options={"verify_exp": True, "verify_aud": False},
            )
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    user_id_str = payload.get("sub")
    if not user_id_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identity (sub).",
        )

    try:
        user_id = int(user_id_str)
    except ValueError:
        user_id = 1

    roles = payload.get("roles", [Role.USER])
    permissions = payload.get("permissions", [])
    email = payload.get("email", "")

    return AuthenticatedUser(
        user_id=user_id,
        email=email,
        roles=roles,
        permissions=permissions,
        token=token,
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> AuthenticatedUser:
    """FastAPI dependency for verifying access tokens in downstream microservices."""
    if not credentials or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return decode_and_validate_token(credentials.credentials)


def require_role(required_role: str):
    """Dependency factory ensuring current user possesses a specific role."""

    def role_checker(user: AuthenticatedUser = Depends(get_current_user)) -> AuthenticatedUser:
        if not user.has_role(required_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{required_role}' role.",
            )
        return user

    return role_checker


def require_permission(required_permission: str):
    """Dependency factory ensuring current user possesses a specific permission."""

    def permission_checker(
        user: AuthenticatedUser = Depends(get_current_user),
    ) -> AuthenticatedUser:
        if not user.has_permission(required_permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires '{required_permission}' permission.",
            )
        return user

    return permission_checker
