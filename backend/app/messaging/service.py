"""Customer notifications (P9): contacts with explicit opt-in, ETAs from the plan, template messages through
the sender adapter (stub only), and a log row for every message sent or not sent.

Rules
* A message goes out only if the customer has a contact AND opt_in is true at send time. Otherwise a log row
  says why not (`skipped_no_contact`, `skipped_no_opt_in`); no message text is stored for those.
* ETA messages need a completed, feasible plan and a shift start (real clock time of the plan's time 0).
  Stops a driver already reported are skipped. An ETA already sent for the same plan and customer is not
  sent again unless `resend` is set.
* Delivered/failed messages follow a driver's report. A sender failure is logged and never undoes the report.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.db.keys import Principal
from app.db.models import CustomerContact, NotificationLog, Plan, StopEvent, Tenant
from app.db.session import tenant_session
from app.distances.service import describe
from app.driver.service import plan_routes
from app.messaging.etas import METHOD, route_etas, time_model_note, unit_seconds
from app.messaging.senders import MessageSender, mask
from app.messaging.templates import REASON_TEXT, render
from app.models.problem import Instance
from app.services.plans import audit

log = logging.getLogger("logimind.messaging")
PHONE = re.compile(r"^\+[1-9][0-9]{6,14}$")  # E.164
EMAIL = re.compile(r"^[^@\s]{1,64}@[A-Za-z0-9.-]{1,255}\.[A-Za-z]{2,}$")


class ContactError(ValueError):
    """Invalid contact (422)."""


class NotifyError(ValueError):
    """The request cannot be served as asked (422)."""


class NotifyConflict(ValueError):
    """The plan is not a completed, feasible plan (409)."""


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).isoformat()


class NotificationService:
    def __init__(self, factory: sessionmaker[Session], sender: MessageSender, clock: Callable[[], float] = time.time):
        self.factory = factory
        self.sender = sender
        self.clock = clock

    def _now(self) -> datetime:
        return datetime.fromtimestamp(self.clock(), tz=timezone.utc)

    # ---- contacts and opt-in ------------------------------------------------
    def set_contact(self, who: Principal, customer_id: int, channel: str, address: str, opt_in: bool,
                    name: str = "") -> dict:
        address = address.strip()
        if channel == "sms" and not PHONE.match(address):
            raise ContactError("an sms address must be a phone number in international form, e.g. +919812345678")
        if channel == "email" and not EMAIL.match(address):
            raise ContactError("not a valid e-mail address")
        if channel not in ("sms", "email"):
            raise ContactError("channel must be sms or email")
        with tenant_session(self.factory, who.tenant_id) as s:
            c = s.scalars(select(CustomerContact).where(CustomerContact.customer_id == customer_id)).first()
            was = bool(c and c.opt_in)
            if c is None:
                c = CustomerContact(tenant_id=who.tenant_id, customer_id=customer_id)
                s.add(c)
            c.channel, c.address, c.name, c.updated_at = channel, address, name, self._now()
            if opt_in and not was:
                c.opt_in, c.opt_in_at = True, self._now()
            elif not opt_in and was:
                c.opt_in, c.opt_out_at = False, self._now()
            elif not opt_in:
                c.opt_in = False
            audit(s, who.tenant_id, who.key_id, "contact.opt_in" if c.opt_in else "contact.opt_out",
                  f"customer:{customer_id}", channel=channel)
            s.commit()
            return self._contact_view(c)

    def _contact_view(self, c: CustomerContact) -> dict:
        return {"customer_id": c.customer_id, "name": c.name, "channel": c.channel, "address": mask(c.address),
                "opt_in": bool(c.opt_in), "opt_in_at": _iso(c.opt_in_at), "opt_out_at": _iso(c.opt_out_at)}

    def list_contacts(self, who: Principal) -> list[dict]:
        with tenant_session(self.factory, who.tenant_id) as s:
            rows = s.scalars(select(CustomerContact).order_by(CustomerContact.customer_id))
            return [self._contact_view(c) for c in rows]

    # ---- ETAs ----------------------------------------------------------------
    def _plan(self, s: Session, plan_id: str) -> tuple[Plan, Instance, list[list[int]]] | None:
        plan = s.get(Plan, plan_id)
        if plan is None:
            return None
        routes = plan_routes(plan)
        if routes is None:
            raise NotifyConflict(f"plan {plan_id} is {plan.state} and not a feasible plan; ETAs need a completed, "
                                 "feasible plan")
        return plan, Instance.from_dict(plan.instance), routes

    def etas(self, who: Principal, plan_id: str, shift_start: datetime | None = None) -> dict | None:
        with tenant_session(self.factory, who.tenant_id) as s:
            found = self._plan(s, plan_id)
            if found is None:
                return None
            _, inst, routes = found
            reported = self._reported(s, plan_id)
        out = []
        for r, route in enumerate(routes):
            for stop in route_etas(inst, route, shift_start):
                out.append({**stop, "route_index": r, "reported": reported.get(stop["customer_id"])})
        return {"plan_id": plan_id, "time_unit": inst.time_unit,
                "time_per_distance": None if inst.road is not None else inst.time_per_distance,
                "distance_source": describe(inst.to_dict()), "time_model": time_model_note(inst),
                "shift_start": _iso(shift_start),
                "clock_times": shift_start is not None and unit_seconds(inst) is not None, "method": METHOD,
                "stops": out}

    def _reported(self, s: Session, plan_id: str) -> dict[int, str]:
        latest: dict[int, str] = {}
        for e in s.scalars(select(StopEvent).where(StopEvent.plan_id == plan_id).order_by(StopEvent.id)):
            latest[e.customer_id] = e.status
        return latest

    # ---- sending ---------------------------------------------------------------
    def _deliver(self, s: Session, tenant_id: str, plan_id: str | None, customer_id: int, template: str,
                 make_text: Callable[[], str]) -> dict:
        """Check the contact and opt-in, send through the adapter, and add the log row. Returns the log view."""
        c = s.scalars(select(CustomerContact).where(CustomerContact.customer_id == customer_id)).first()
        row = NotificationLog(tenant_id=tenant_id, plan_id=plan_id, customer_id=customer_id, template=template,
                              provider=self.sender.name)
        if c is None:
            row.status = "skipped_no_contact"
        elif not c.opt_in:
            row.status, row.channel, row.recipient = "skipped_no_opt_in", c.channel, mask(c.address)
        else:
            text = make_text()
            res = self.sender.send(c.channel, c.address, text)
            row.channel, row.recipient, row.message = c.channel, mask(c.address), text
            row.status = "sent_stub" if res.ok and self.sender.name == "stub" else ("sent" if res.ok else "failed")
            row.error = res.error
        row.at = self._now()
        s.add(row)
        return self._log_view(row)

    def _log_view(self, n: NotificationLog) -> dict:
        return {"plan_id": n.plan_id, "customer_id": n.customer_id, "template": n.template, "channel": n.channel,
                "recipient": n.recipient, "message": n.message, "status": n.status, "provider": n.provider,
                "error": n.error, "at": _iso(n.at)}

    def send_etas(self, who: Principal, plan_id: str, shift_start: datetime, route_index: int | None = None,
                  resend: bool = False) -> dict | None:
        if shift_start.tzinfo is None:
            raise NotifyError("shift_start needs a time zone, e.g. 2027-01-15T08:00:00+05:30")
        with tenant_session(self.factory, who.tenant_id) as s:
            found = self._plan(s, plan_id)
            if found is None:
                return None
            _, inst, routes = found
            if unit_seconds(inst) is None:
                raise NotifyError(f"time unit {inst.time_unit!r} is not a clock unit (s, min, h); no clock ETAs")
            if route_index is not None and not 0 <= route_index < len(routes):
                raise NotifyError(f"route_index must be between 0 and {len(routes) - 1}")
            company = s.get(Tenant, who.tenant_id).name
            reported = self._reported(s, plan_id)
            already = {n.customer_id for n in s.scalars(select(NotificationLog).where(
                NotificationLog.plan_id == plan_id, NotificationLog.template == "eta",
                NotificationLog.status.in_(("sent", "sent_stub"))))}
            results = []
            for r, route in enumerate(routes):
                if route_index is not None and r != route_index:
                    continue
                for stop in route_etas(inst, route, shift_start):
                    cid = stop["customer_id"]
                    if cid in reported:
                        results.append({"customer_id": cid, "status": "skipped_already_reported"})
                        continue
                    if cid in already and not resend:
                        results.append({"customer_id": cid, "status": "skipped_already_sent"})
                        continue
                    eta_time = datetime.fromisoformat(stop["eta"]).strftime("%H:%M")
                    view = self._deliver(s, who.tenant_id, plan_id, cid, "eta",
                                         lambda t=eta_time: render("eta", company=company, eta_time=t))
                    results.append({**view, "eta": stop["eta"]})
            counts: dict[str, int] = {}
            for x in results:
                counts[x["status"]] = counts.get(x["status"], 0) + 1
            audit(s, who.tenant_id, who.key_id, "notify.etas", plan_id, counts=counts, provider=self.sender.name)
            s.commit()
        return {"plan_id": plan_id, "provider": self.sender.name, "method": METHOD,
                "time_model": time_model_note(inst), "counts": counts, "results": results}

    def on_stop_event(self, tenant_id: str, plan_id: str, customer_id: int, status: str, reason: str | None) -> None:
        """Called after a driver's report is stored. Never raises: a failure is logged, the report stands."""
        try:
            with tenant_session(self.factory, tenant_id) as s:
                company = s.get(Tenant, tenant_id).name
                if status == "delivered":
                    make = lambda: render("delivered", company=company)  # noqa: E731
                else:
                    make = lambda: render("failed", company=company,  # noqa: E731
                                          reason=REASON_TEXT.get(reason or "other", REASON_TEXT["other"]))
                self._deliver(s, tenant_id, plan_id, customer_id, status, make)
                s.commit()
        except Exception:  # reported in the server log; the driver's report is already stored
            log.exception("notification after a stop report failed (tenant %s, plan %s)", tenant_id, plan_id)

    def log(self, who: Principal, plan_id: str | None = None, limit: int = 200) -> list[dict]:
        with tenant_session(self.factory, who.tenant_id) as s:
            q = select(NotificationLog).order_by(NotificationLog.id.desc()).limit(max(1, min(limit, 1000)))
            if plan_id:
                q = q.where(NotificationLog.plan_id == plan_id)
            return [self._log_view(n) for n in s.scalars(q)]
