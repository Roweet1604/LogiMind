"""Customer message templates. Fixed text with named fields; every field must be filled (no free text
from a model or a user ends up in a message except the company name the tenant chose)."""
from __future__ import annotations

from string import Template

TEMPLATES = {
    "eta": Template("$company: your delivery is planned for around $eta_time today. This is an estimate from "
                    "our route plan and can change."),
    "delivered": Template("$company: your delivery has been completed. Thank you."),
    "failed": Template("$company: we could not complete your delivery today ($reason). We will contact you to "
                       "arrange a new time."),
}
REASON_TEXT = {
    "not_home": "nobody was available", "refused": "the delivery was refused",
    "wrong_address": "the address could not be found", "access_problem": "we could not get access",
    "damaged": "the goods were damaged", "other": "an unexpected problem",
}


def render(name: str, **fields: str) -> str:
    """Raises KeyError if a field is missing, so a message is never sent with a blank or "$field" in it."""
    return TEMPLATES[name].substitute(**fields)
