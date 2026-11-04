"""P8 dispatch copilot: natural language -> constrained Pydantic intents -> solver tools -> grounded replies.

The LLM never produces routes: no intent schema has a route field, and every plan comes from a solver
tool and the validator (CLAUDE.md invariant 1).
"""
