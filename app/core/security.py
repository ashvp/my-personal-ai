import secrets
from typing import Optional
from fastapi import Security, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import settings

# This registers "X-Device-Token" in FastAPI OpenAPI / Swagger UI
device_token_header = APIKeyHeader(
    name="X-Device-Token",
    auto_error=False,
    description="Pre-shared device token identifying authorized devices"
)


async def verify_device_token(
    token: Optional[str] = Security(device_token_header)
) -> str:
    """Validates that the incoming request contains an authorized device token.

    Rejects unauthenticated requests with 401 Unauthorized before
    any compute resources or LLM calls are triggered.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing device authentication. Please provide 'X-Device-Token' header.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    authorized_tokens = settings.get_authorized_tokens()
    # Constant-time comparison to prevent timing attacks
    is_valid = any(secrets.compare_digest(token, auth_token) for auth_token in authorized_tokens)

    if not is_valid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized device. Token rejected.",
            headers={"WWW-Authenticate": "ApiKey"}
        )

    return token
