"""Driver access to one route (P9).

* Dispatchers (API key) create a signed, short-lived link for one route of a completed, feasible plan,
  list and revoke links, and read the stop reports and photos.
* Drivers (link token only) read their stop list, report a stop delivered or failed with a reason, and
  upload a proof-of-delivery photo. Every driver call is checked against the link: tenant, plan and route.
  A customer that is not on the link's route is answered with 404, the same as a customer that does not exist.

Reports do NOT change the plan. Replanning after a failed delivery stays a dispatcher decision
(POST /api/plans/{id}/replan), so nothing changes an active plan without a person confirming it.
"""
from __future__ import annotations

import hashlib
import os
import re
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from app.db.keys import Principal
from app.db.models import DriverLink, Plan, PodPhoto, StopEvent, Tenant
from app.db.session import admin_session, tenant_session
from app.driver.links import LinkClaims, LinkError, LinkSigner
from app.models.problem import Instance
from app.services.plans import audit

FAIL_REASONS = ("not_home", "refused", "wrong_address", "access_problem", "damaged", "other")
STATUSES = ("delivered", "failed")
DEFAULT_TTL_MIN = 12 * 60
MAX_TTL_MIN = 24 * 60
MIN_TTL_MIN = 5
MAX_PHOTO_BYTES = 3 * 1024 * 1024
MAX_PHOTOS_PER_STOP = 5
# Detected from the file's first bytes; the client's declared type and file name are ignored.
PHOTO_TYPES = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}
_SAFE_ID = re.compile(r"^[a-z]+-[0-9a-f]{12}$")


class DriverRequestError(ValueError):
    """Invalid request (422)."""


class DriverConflict(ValueError):
    """The request conflicts with stored state (409)."""


class NotOnRoute(LookupError):
    """The customer is not on this link's route, or the object does not exist for this tenant (404)."""


def sniff_image(data: bytes) -> str | None:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def plan_routes(plan: Plan) -> list[list[int]] | None:
    """The stored routes of a completed, feasible plan (vehicle order); None otherwise."""
    result = plan.result or {}
    feasible = result.get("feasible", (result.get("validation") or {}).get("feasible"))
    if plan.state != "completed" or not feasible:
        return None
    return result.get("routes") or (result.get("solve") or {}).get("routes")


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


class DriverService:
    def __init__(self, factory: sessionmaker[Session], data_dir: Path, signer: LinkSigner,
                 clock: Callable[[], float] = time.time, app_url: str | None = None, on_stop_event=None):
        self.factory = factory
        self.photo_dir = Path(data_dir) / "pod"
        self.signer = signer
        self.clock = clock
        self.app_url = (app_url or os.environ.get("LOGIMIND_DRIVER_APP_URL", "http://localhost:5174")).rstrip("/")
        self.on_stop_event = on_stop_event  # P9 notifications: f(tenant_id, plan_id, customer_id, status, reason)

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self.clock(), tz=timezone.utc)

    # ---- dispatcher side (API key) ------------------------------------------
    def create_link(self, who: Principal, plan_id: str, route_index: int, ttl_minutes: int = DEFAULT_TTL_MIN,
                    label: str = "") -> dict | None:
        if not MIN_TTL_MIN <= ttl_minutes <= MAX_TTL_MIN:
            raise DriverRequestError(f"ttl_minutes must be between {MIN_TTL_MIN} and {MAX_TTL_MIN}")
        with tenant_session(self.factory, who.tenant_id) as s:
            plan = s.get(Plan, plan_id)
            if plan is None:
                return None
            routes = plan_routes(plan)
            if routes is None:
                raise DriverConflict(f"plan {plan_id} is {plan.state} and not a feasible plan; "
                                     "driver links are only made for completed, feasible plans")
            if not 0 <= route_index < len(routes):
                raise DriverRequestError(f"route_index must be between 0 and {len(routes) - 1}")
            if not routes[route_index]:
                raise DriverRequestError(f"route {route_index} has no stops")
            expires = int(self.clock()) + ttl_minutes * 60
            link = DriverLink(id=f"dlk-{uuid.uuid4().hex[:12]}", tenant_id=who.tenant_id, plan_id=plan_id,
                              route_index=route_index, label=label, created_by=who.key_id,
                              expires_at=datetime.fromtimestamp(expires, tz=timezone.utc))
            s.add(link)
            audit(s, who.tenant_id, who.key_id, "driver_link.create", link.id, plan_id=plan_id,
                  route_index=route_index, ttl_minutes=ttl_minutes)
            s.commit()
            token = self.signer.sign(LinkClaims(link.id, who.tenant_id, plan_id, route_index, expires))
            # The token goes in the URL fragment (#), which browsers never send to servers or proxies.
            return {**self._link_view(link), "token": token, "url": f"{self.app_url}/#t={token}"}

    def _link_view(self, link: DriverLink) -> dict:
        return {"link_id": link.id, "plan_id": link.plan_id, "route_index": link.route_index, "label": link.label,
                "created_at": _iso(link.created_at), "expires_at": _iso(link.expires_at),
                "revoked_at": _iso(link.revoked_at)}

    def list_links(self, who: Principal, plan_id: str) -> list[dict] | None:
        with tenant_session(self.factory, who.tenant_id) as s:
            if s.get(Plan, plan_id) is None:
                return None
            rows = s.scalars(select(DriverLink).where(DriverLink.plan_id == plan_id).order_by(DriverLink.created_at))
            return [self._link_view(r) for r in rows]

    def revoke_link(self, who: Principal, link_id: str) -> dict | None:
        with tenant_session(self.factory, who.tenant_id) as s:
            link = s.get(DriverLink, link_id)
            if link is None:
                return None
            if link.revoked_at is None:
                link.revoked_at = self._now()
                audit(s, who.tenant_id, who.key_id, "driver_link.revoke", link_id, plan_id=link.plan_id)
                s.commit()
            return self._link_view(link)

    def stop_reports(self, who: Principal, plan_id: str) -> dict | None:
        """Every stop report and photo of a plan, oldest first, for the ops console."""
        with tenant_session(self.factory, who.tenant_id) as s:
            if s.get(Plan, plan_id) is None:
                return None
            events = s.scalars(select(StopEvent).where(StopEvent.plan_id == plan_id).order_by(StopEvent.id))
            photos = s.scalars(select(PodPhoto).where(PodPhoto.plan_id == plan_id).order_by(PodPhoto.created_at))
            return {"plan_id": plan_id, "events": [self._event_view(e) for e in events],
                    "photos": [self._photo_view(p) for p in photos]}

    def photo_file(self, who: Principal, photo_id: str) -> tuple[Path, str] | None:
        with tenant_session(self.factory, who.tenant_id) as s:
            photo = s.get(PodPhoto, photo_id)
            if photo is None:
                return None
            path = self._photo_path(photo.tenant_id, photo.id, photo.content_type)
            return (path, photo.content_type) if path.is_file() else None

    # ---- driver side (link token) -------------------------------------------
    def resolve(self, token: str | None) -> LinkClaims:
        """Verify the signature and expiry, then check the link row: it must exist, not be revoked, and
        name the same tenant, plan and route as the signed claims."""
        claims = self.signer.verify(token, self.clock())
        with admin_session(self.factory) as s:
            row = s.get(DriverLink, claims.link_id)
            if row is None or row.revoked_at is not None:
                raise LinkError("driver link has been revoked")
            if (row.tenant_id, row.plan_id, row.route_index) != (claims.tenant_id, claims.plan_id,
                                                                 claims.route_index):
                raise LinkError("driver link does not match its record")
        return claims

    def _load(self, s: Session, c: LinkClaims) -> tuple[Plan, Instance, list[int]]:
        plan = s.get(Plan, c.plan_id)  # tenant session: another tenant's plan is invisible
        routes = plan_routes(plan) if plan is not None else None
        if routes is None or c.route_index >= len(routes):
            raise LinkError("the plan for this driver link is no longer available")
        return plan, Instance.from_dict(plan.instance), list(routes[c.route_index])

    def route_view(self, c: LinkClaims) -> dict:
        with tenant_session(self.factory, c.tenant_id) as s:
            plan, inst, stops = self._load(s, c)
            latest = self._latest_status(s, c)
            photos: dict[int, int] = {}
            for p in s.scalars(select(PodPhoto).where(PodPhoto.plan_id == c.plan_id,
                                                      PodPhoto.route_index == c.route_index)):
                photos[p.customer_id] = photos.get(p.customer_id, 0) + 1
            child = s.scalars(select(Plan.id).where(Plan.parent_id == c.plan_id)).first()
            tenant = s.get(Tenant, c.tenant_id)
            by_id = {cu.id: cu for cu in inst.customers}
            geo = inst.metric == "haversine"
            out = []
            for seq, cid in enumerate(stops, start=1):
                cu = by_id[cid]
                ev = latest.get(cid)
                out.append({"seq": seq, "customer_id": cid, "demand": cu.demand, "x": cu.x, "y": cu.y,
                            "lat": cu.y if geo else None, "lon": cu.x if geo else None,
                            "ready_time": cu.ready_time, "due_time": cu.due_time, "service_time": cu.service_time,
                            "status": ev.status if ev else "pending", "reason": ev.reason if ev else None,
                            "reported_at": _iso(ev.received_at) if ev else None, "photos": photos.get(cid, 0)})
            return {"plan_id": c.plan_id, "route_index": c.route_index, "plan_name": inst.name,
                    "company": tenant.name if tenant else "", "expires_at": _iso(datetime.fromtimestamp(
                        c.expires, tz=timezone.utc)),
                    "coordinates": "lon/lat" if geo else "planar (no map coordinates)",
                    "time_unit": inst.time_unit, "superseded_by": child, "stops": out,
                    "fail_reasons": list(FAIL_REASONS)}

    def _latest_status(self, s: Session, c: LinkClaims) -> dict[int, StopEvent]:
        latest: dict[int, StopEvent] = {}
        for e in s.scalars(select(StopEvent).where(StopEvent.plan_id == c.plan_id,
                                                   StopEvent.route_index == c.route_index).order_by(StopEvent.id)):
            latest[e.customer_id] = e
        return latest

    def record_status(self, c: LinkClaims, customer_id: int, status: str, reason: str | None, note: str,
                      client_event_id: str, occurred_at: datetime | None) -> dict:
        if status not in STATUSES:
            raise DriverRequestError(f"status must be one of {', '.join(STATUSES)}")
        if status == "failed" and reason not in FAIL_REASONS:
            raise DriverRequestError(f"a failed stop needs a reason: one of {', '.join(FAIL_REASONS)}")
        if status == "delivered" and reason is not None:
            raise DriverRequestError("a delivered stop takes no failure reason")
        if reason == "other" and not note.strip():
            raise DriverRequestError("reason 'other' needs a note")
        with tenant_session(self.factory, c.tenant_id) as s:
            _, _, stops = self._load(s, c)
            if customer_id not in stops:
                raise NotOnRoute(f"customer {customer_id} is not on this route")
            dup = s.scalars(select(StopEvent).where(StopEvent.client_event_id == client_event_id)).first()
            if dup is not None:
                return self._duplicate(dup, c, customer_id, status)
            ev = StopEvent(tenant_id=c.tenant_id, plan_id=c.plan_id, route_index=c.route_index,
                           customer_id=customer_id, status=status, reason=reason, note=note.strip(),
                           link_id=c.link_id, client_event_id=client_event_id, occurred_at=occurred_at)
            s.add(ev)
            audit(s, c.tenant_id, c.link_id, f"stop.{status}", c.plan_id, route_index=c.route_index,
                  customer_id=customer_id, reason=reason)
            try:
                s.commit()
            except IntegrityError:  # the same update arrived twice at once
                s.rollback()
                dup = s.scalars(select(StopEvent).where(StopEvent.client_event_id == client_event_id)).first()
                return self._duplicate(dup, c, customer_id, status)
            view = {**self._event_view(ev), "duplicate": False}
        if self.on_stop_event is not None:
            self.on_stop_event(c.tenant_id, c.plan_id, customer_id, status, reason)
        return view

    def _duplicate(self, dup: StopEvent, c: LinkClaims, customer_id: int, status: str) -> dict:
        """A resent offline update is answered with the stored event; a reused id for something else is a conflict."""
        if (dup.plan_id, dup.route_index, dup.customer_id, dup.status) != (c.plan_id, c.route_index, customer_id,
                                                                            status):
            raise DriverConflict("client_event_id was already used for a different update")
        return {**self._event_view(dup), "duplicate": True}

    def _event_view(self, e: StopEvent) -> dict:
        return {"event_id": e.id, "plan_id": e.plan_id, "route_index": e.route_index, "customer_id": e.customer_id,
                "status": e.status, "reason": e.reason, "note": e.note, "client_event_id": e.client_event_id,
                "occurred_at": _iso(e.occurred_at), "received_at": _iso(e.received_at), "link_id": e.link_id}

    def _photo_path(self, tenant_id: str, photo_id: str, content_type: str) -> Path:
        if not (_SAFE_ID.match(tenant_id) and _SAFE_ID.match(photo_id)):  # our own ids; never user input
            raise ValueError("unsafe photo path")
        return self.photo_dir / tenant_id / f"{photo_id}{PHOTO_TYPES[content_type]}"

    def _photo_view(self, p: PodPhoto) -> dict:
        return {"photo_id": p.id, "plan_id": p.plan_id, "route_index": p.route_index, "customer_id": p.customer_id,
                "content_type": p.content_type, "size_bytes": p.size_bytes, "sha256": p.sha256,
                "created_at": _iso(p.created_at)}

    def save_photo(self, c: LinkClaims, customer_id: int, data: bytes) -> dict:
        if not data:
            raise DriverRequestError("the photo is empty")
        if len(data) > MAX_PHOTO_BYTES:
            raise DriverRequestError(f"photo larger than {MAX_PHOTO_BYTES // (1024 * 1024)} MB")
        ctype = sniff_image(data)
        if ctype is None:
            raise DriverRequestError("photo must be a JPEG, PNG or WebP image")
        with tenant_session(self.factory, c.tenant_id) as s:
            _, _, stops = self._load(s, c)
            if customer_id not in stops:
                raise NotOnRoute(f"customer {customer_id} is not on this route")
            count = len(s.scalars(select(PodPhoto.id).where(PodPhoto.plan_id == c.plan_id,
                                                            PodPhoto.customer_id == customer_id)).all())
            if count >= MAX_PHOTOS_PER_STOP:
                raise DriverConflict(f"at most {MAX_PHOTOS_PER_STOP} photos per stop")
            photo = PodPhoto(id=f"pod-{uuid.uuid4().hex[:12]}", tenant_id=c.tenant_id, plan_id=c.plan_id,
                             route_index=c.route_index, customer_id=customer_id, link_id=c.link_id,
                             content_type=ctype, size_bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
            path = self._photo_path(c.tenant_id, photo.id, ctype)
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".part")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            s.add(photo)
            audit(s, c.tenant_id, c.link_id, "stop.photo", c.plan_id, route_index=c.route_index,
                  customer_id=customer_id, photo_id=photo.id, size_bytes=len(data))
            try:
                s.commit()
            except Exception:
                path.unlink(missing_ok=True)  # the file we just wrote has no record
                raise
            return self._photo_view(photo)
