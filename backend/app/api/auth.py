"""API-key authentication for tenant endpoints. Send the key as `X-API-Key: lm_...`."""
from __future__ import annotations

import math

from fastapi import Depends, HTTPException, Request
from fastapi.security import APIKeyHeader

from app.db.keys import Principal, authenticate
from app.db.session import admin_session

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False,
                              description="Tenant API key (created with `python manage.py create-tenant`).")


def require_principal(request: Request, key: str | None = Depends(api_key_header)) -> Principal:
    with admin_session(request.app.state.db) as s:
        principal = authenticate(s, key)
    if principal is None:
        raise HTTPException(401, detail="missing, invalid or revoked API key", headers={"WWW-Authenticate": "API-Key"})
    allowed, retry_s = request.app.state.ratelimiter.check(principal.key_id)
    if not allowed:
        raise HTTPException(429, detail="rate limit exceeded for this API key",
                            headers={"Retry-After": str(max(1, math.ceil(retry_s)))})
    return principal
