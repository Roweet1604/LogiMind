# 0017: ETA notifications with a stub sender (P9)

Date: 4 Nov 2026. Status: accepted (decided unattended by Claude Code).

## Decision
- **Adapter, stub only.** `app/messaging/senders.py` defines `MessageSender`. The only implementation, `StubSender`, logs the message (recipient masked) and keeps it in memory. It never opens a network connection.
  - `LOGIMIND_NOTIFY_PROVIDER` accepts only `stub`; any other value stops start-up with an error.
  - No SMS or e-mail provider is built in (zero cost; PLAN.md defers a real provider). A real provider would be one more class behind the same interface.
- **Log table** `notification_log` (migration 0005). It records every message sent or **not** sent:
  - Statuses: `sent_stub`, `failed` (with the error), `skipped_no_contact`, `skipped_no_opt_in`.
  - The recipient is stored masked (`+91********78`, `a***@example.com`).
  - Message text is stored only for messages that were sent.
  - `GET /api/notifications[?plan_id=]` lists the log.
- **Opt-in.** `customer_contacts` holds one row per tenant and customer id, with channel `sms` (E.164 number) or `email`. `PUT /api/contacts/{customer_id}` sets it.
  - `opt_in` defaults to false; the dispatcher must state it, and a message goes out only while it is true.
  - `opt_in_at` and `opt_out_at` record when it changed, and each change writes an audit row.
  - Contacts are keyed by the customer id used in the tenant's orders, since there is no separate customer master yet.
- **ETAs come from the plan.** `app/messaging/etas.py` uses the validator's `route_schedule`: travel = distance x `time_per_distance`, waiting when early, and service times. So the ETA is the same schedule the validator checks.
  - Clock times need `shift_start`, a time-zone-aware real time for the plan's time 0. Time units must be `s`, `min` or `h`; other units give relative values only, and sending is refused (422).
  - Every response states `method` ("not live traffic") and `time_model`. A plan with no time data uses the model default, 1 min per km (about 60 km/h), and the response says "default assumption" rather than hiding it.
- **Sending ETAs.** `POST /api/plans/{id}/notify-etas {shift_start, route_index?, resend?}` works only for completed, feasible plans (409 otherwise).
  - It skips stops a driver already reported, and customers who already got an ETA for this plan unless `resend` is set.
  - It returns counts per status, and every customer gets a log row.
- **After driver reports:** a delivered or failed report sends the matching template to an opted-in customer; for failures, the reason is turned into plain words. A sender error is logged and never undoes the stored report (tested).
- **Templates** (`templates.py`) are fixed text with named fields, filled with `string.Template.substitute`, so a missing field raises instead of sending "$field". No LLM text and no free text goes into a message; the only tenant-chosen value is the company name. The delivered message has no clock time, because tenants have no time-zone setting yet.

## Not done
- No real delivery, no delivery receipts, no inbound "STOP" handling (a stub cannot receive replies). Opt-out is set by the dispatcher.
- ETAs are not recomputed from the driver's actual progress. They are the planned times, and a delayed route is not re-announced.
- There is no ops-console screen for contacts or the notification log yet (API only).
