# 0002: Phase 0 answers and defaults

Date: 2 Nov 2026. Status: accepted.

## Answered by the team
- LLM: local model only (Ollama). Messaging: stub only. Cloud budget: zero.
- Docker and Ollama are not installed yet. They become explicit setup steps before the phases that need them (Docker before P4/P6, Ollama before P8).
- Cut line: the proposed cut line is approved, provided every must-have in Prompt A section 4 stays in. If the weeks remaining make that impossible, a new cut line is shown to the team and waits for approval.

## Still open (the answer template came back with the placeholders unfilled)
Weeks remaining, next review/demo dates, workstream owners, pilot data, mentor's expected deliverables. Until answered: no cut is made, nothing is assumed about dates, and no pilot data is claimed.

## Defaults chosen (team said "use your recommended default")
- Laptop hardware: assume 8 GB RAM and no GPU. Default copilot model `llama3.2:3b`; use `qwen2.5:7b-instruct` where a laptop has 16 GB or more. Record the model actually used with every evaluation.
- OSRM: one small regional extract (Karnataka from Geofabrik). If a laptop cannot preprocess it, the haversine fallback is used and flagged in every plan.
- Demo CSV files from the Product Guide (not in docs/context): regenerate equivalent instances from the generator with recorded seeds when needed, and label them as regenerated. Do not claim they are the original files.
- Python virtual environments and node_modules go outside OneDrive (for example `%TEMP%`), because OneDrive syncs thousands of small files and Windows path-length limits break installs.
