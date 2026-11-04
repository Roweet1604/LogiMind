"""Driver endpoints (P9).

Dispatcher side (`X-API-Key`): create, list and revoke driver links; read stop reports and photos.
Driver side (`X-Driver-Token`, the token from the link): the route's stop list, delivered/failed
reports and proof-of-delivery photos. A driver token works only for its own route; it never
works on the tenant endpoints, and an API key never works on the driver endpoints.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from app.api.auth import require_principal
from app.db.keys import Principal
from app.driver.links import LinkClaims, LinkError
from app.driver.service import (
    DEFAULT_TTL_MIN,
    FAIL_REASONS,
    MAX_PHOTO_BYTES,
    MAX_TTL_MIN,
    MIN_TTL_MIN,
    DriverConflict,
    DriverRequestError,
    NotOnRoute,
)

router = APIRouter(prefix="/api", tags=["driver"])
driver_token_header = APIKeyHeader(name="X-Driver-Token", auto_error=False,
                                   description="Token from a driver link (the part after `#t=`).")


class DriverLinkIn(BaseModel):
    route_index: int = Field(ge=0)
    ttl_minutes: int = Field(DEFAULT_TTL_MIN, ge=MIN_TTL_MIN, le=MAX_TTL_MIN)
    label: str = Field("", max_length=200)


class StopStatusIn(BaseModel):
    status: Literal["delivered", "failed"]
    reason: Literal[FAIL_REASONS] | None = None  # required when failed
    note: str = Field("", max_length=500)
    client_event_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$",
                                 description="Unique per update (e.g. a UUID); resending it is safe.")
    occurred_at: datetime | None = Field(None, description="When it happened, by the driver's phone clock.")


def _errors(fn, *args):
    try:
        return fn(*args)
    except DriverRequestError as exc:
        raise HTTPException(422, detail=str(exc))
    except DriverConflict as exc:
        raise HTTPException(409, detail=str(exc))
    except NotOnRoute as exc:
        raise HTTPException(404, detail=str(exc))
    except LinkError as exc:
        raise HTTPException(401, detail=str(exc), headers={"WWW-Authenticate": "Driver-Token"})


def require_link(request: Request, token: str | None = Depends(driver_token_header)) -> LinkClaims:
    claims = _errors(request.app.state.driver.resolve, token)
    allowed, retry_s = request.app.state.ratelimiter.check(f"link:{claims.link_id}")
    if not allowed:
        raise HTTPException(429, detail="rate limit exceeded for this driver link",
                            headers={"Retry-After": str(max(1, math.ceil(retry_s)))})
    return claims


# ---- dispatcher side -----------------------------------------------------------
@router.post("/plans/{plan_id}/driver-links", status_code=201)
def create_driver_link(plan_id: str, body: DriverLinkIn, request: Request,
                       who: Principal = Depends(require_principal)) -> dict:
    """A short-lived link for one route of a completed, feasible plan. The token is returned once;
    send the `url` to the driver. Default lifetime 12 h, at most 24 h."""
    out = _errors(request.app.state.driver.create_link, who, plan_id, body.route_index, body.ttl_minutes,
                  body.label)
    if out is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return out


@router.get("/plans/{plan_id}/driver-links")
def list_driver_links(plan_id: str, request: Request, who: Principal = Depends(require_principal)) -> list[dict]:
    out = request.app.state.driver.list_links(who, plan_id)
    if out is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return out


@router.delete("/driver-links/{link_id}")
def revoke_driver_link(link_id: str, request: Request, who: Principal = Depends(require_principal)) -> dict:
    out = request.app.state.driver.revoke_link(who, link_id)
    if out is None:
        raise HTTPException(404, detail=f"driver link {link_id} not found")
    return out


@router.get("/plans/{plan_id}/stop-reports")
def stop_reports(plan_id: str, request: Request, who: Principal = Depends(require_principal)) -> dict:
    """Drivers' delivered/failed reports and photo records for a plan, oldest first."""
    out = request.app.state.driver.stop_reports(who, plan_id)
    if out is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return out


@router.get("/photos/{photo_id}")
def get_photo(photo_id: str, request: Request, who: Principal = Depends(require_principal)) -> FileResponse:
    found = request.app.state.driver.photo_file(who, photo_id)
    if found is None:
        raise HTTPException(404, detail=f"photo {photo_id} not found")
    path, ctype = found
    return FileResponse(path, media_type=ctype, headers={"X-Content-Type-Options": "nosniff",
                                                        "Cache-Control": "private, no-store"})


# ---- driver side ---------------------------------------------------------------
@router.get("/driver/route")
def driver_route(request: Request, link: LinkClaims = Depends(require_link)) -> dict:
    """The link's route: stops in order with their latest status. `lat`/`lon` are set only for lon/lat plans."""
    return _errors(request.app.state.driver.route_view, link)


@router.post("/driver/stops/{customer_id}/status")
def driver_stop_status(customer_id: int, body: StopStatusIn, request: Request,
                       link: LinkClaims = Depends(require_link)) -> dict:
    """Report a stop delivered, or failed with a reason. Resending the same client_event_id returns the
    stored report (`duplicate: true`), so queued offline updates can be retried safely."""
    return _errors(request.app.state.driver.record_status, link, customer_id, body.status, body.reason, body.note,
                   body.client_event_id, body.occurred_at)


@router.post("/driver/stops/{customer_id}/photo", status_code=201)
async def driver_stop_photo(customer_id: int, request: Request, file: UploadFile = File(...),
                            link: LinkClaims = Depends(require_link)) -> dict:
    """Proof-of-delivery photo: JPEG, PNG or WebP (checked from the file's bytes), at most 3 MB,
    at most 5 per stop. Stored under a generated name; the uploaded file name is ignored."""
    data = await file.read(MAX_PHOTO_BYTES + 1)
    if len(data) > MAX_PHOTO_BYTES:
        raise HTTPException(413, detail=f"photo larger than {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
    return _errors(request.app.state.driver.save_photo, link, customer_id, data)
