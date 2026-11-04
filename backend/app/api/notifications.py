"""Customer notification endpoints (P9). Messages go through the stub sender only: they are logged, never sent."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import AwareDatetime, BaseModel, Field

from app.api.auth import require_principal
from app.db.keys import Principal
from app.messaging.service import ContactError, NotifyConflict, NotifyError

router = APIRouter(prefix="/api", tags=["notifications"])


class ContactIn(BaseModel):
    channel: Literal["sms", "email"]
    address: str = Field(min_length=3, max_length=320)
    opt_in: bool = Field(description="True only if the customer agreed to receive delivery messages.")
    name: str = Field("", max_length=200)


class NotifyEtasIn(BaseModel):
    shift_start: AwareDatetime = Field(description="Real clock time of the plan's time 0, with a time zone.")
    route_index: int | None = Field(None, ge=0)
    resend: bool = False


def _call(fn, *args):
    try:
        return fn(*args)
    except (ContactError, NotifyError) as exc:
        raise HTTPException(422, detail=str(exc))
    except NotifyConflict as exc:
        raise HTTPException(409, detail=str(exc))


@router.put("/contacts/{customer_id}")
def put_contact(customer_id: int, body: ContactIn, request: Request,
                who: Principal = Depends(require_principal)) -> dict:
    """Create or update a customer's contact. Messages are sent only while opt_in is true; opting out
    is recorded with its time. Addresses are returned masked."""
    return _call(request.app.state.notifications.set_contact, who, customer_id, body.channel, body.address,
                 body.opt_in, body.name)


@router.get("/contacts")
def list_contacts(request: Request, who: Principal = Depends(require_principal)) -> list[dict]:
    return request.app.state.notifications.list_contacts(who)


@router.get("/plans/{plan_id}/etas")
def plan_etas(plan_id: str, request: Request, shift_start: AwareDatetime | None = None,
              who: Principal = Depends(require_principal)) -> dict:
    """Planned arrival (service start) per stop from the plan's own schedule. Clock times only with shift_start."""
    out = _call(request.app.state.notifications.etas, who, plan_id, shift_start)
    if out is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return out


@router.post("/plans/{plan_id}/notify-etas")
def notify_etas(plan_id: str, body: NotifyEtasIn, request: Request,
                who: Principal = Depends(require_principal)) -> dict:
    """Send ETA messages to opted-in customers of a plan (stub: logged, not sent). Every customer gets a
    log row saying what happened."""
    out = _call(request.app.state.notifications.send_etas, who, plan_id, body.shift_start, body.route_index,
                body.resend)
    if out is None:
        raise HTTPException(404, detail=f"plan {plan_id} not found")
    return out


@router.get("/notifications")
def notification_log(request: Request, plan_id: str | None = None, limit: int = 200,
                     who: Principal = Depends(require_principal)) -> list[dict]:
    """The tenant's notification log, newest first (recipients masked)."""
    return request.app.state.notifications.log(who, plan_id, limit)
