# LogiMind plan

Status: **Phase 0 plan (2 Nov 2026)**. The team approved the cut-line approach with all section 4 must-haves kept. Weeks remaining and review dates are still unanswered (see docs/decisions/0002), so the plan currently keeps every must-have. If the weeks turn out too few, a new cut line goes to the team for approval first.

## Setup steps (before the phases that need them)
- **Before P4/P6:** install Docker Desktop with WSL2 on every demo laptop; check `docker --version` and `docker compose version`.
- **Before P8:** install Ollama and pull the default model (`ollama pull llama3.2:3b`; `qwen2.5:7b-instruct` on 16 GB laptops); check `ollama --version`.

## Phases
Effort is a rough estimate in *team-weeks* (all three members working on the phase). It assumes part-time student hours and will be corrected after P1 shows our real pace.

| Phase | Content | Est. team-weeks | Depends on |
| --- | --- | --- | --- |
| P1 | Time windows + service times in the model, OR-Tools time dimension, GA penalty + repair, validator/metrics lateness, migrate baseline, Solomon + CVRPLIB import with provenance, best-known table | 1.5 | - |
| P2 | OR-Tools audit: first-solution x metaheuristic x budget x seeds; defaults per budget class; run-to-run variation | 0.5 | P1 |
| P3 | Hybrid (OR-Tools seeds the GA, optional local search), equal-clock comparison, ablations | 1.0 | P1, P2 |
| P4 | DistanceProvider (haversine + self-hosted OSRM), cache, flagged fallback, travel times | 1.0 | P1 |
| P5 | Selector: features, dataset generator, grouped CV, baselines, accuracy + regret, model card, `engine=auto` | 1.5 | P2, P3 |
| P6 | Platform: plans API, replan endpoint, webhooks, CSV/Excel import, API keys, tenants, DB, jobs, Docker Compose, isolation tests | 2.0 | P1 |
| P7 | Replanning: breakdown, failed delivery, urgent order; freeze completed stops; warm start; timing | 1.0 | P3, P6 |
| P8 | Copilot: LangGraph + Ollama, six tools, Pydantic schemas, clarify/confirm/refuse, fake LLM, chat panel, eval set | 2.0 | P3, P6 |
| P9 | Driver PWA (stop list, deep link, delivered/failed, photo, offline), stub notifications | 1.5 | P6 |
| P10 | Evaluation runs, tables, figures, docs, deck material | 1.5 | all |
| | **Total** | **~13.5** | |

**Status:** P1 done on 2 Nov 2026 (see PROGRESS.md). Gehring-Homberger was not imported (optional). Notes carried forward: P2 must audit time-window instances separately (the default OR-Tools start strategy failed on R101); P3 must fix the GA's excess routes on time-window instances.

**Status:** P2 done on 2 Nov 2026: OR-Tools audit (1728 runs) and audited defaults per problem type and budget class (docs/decisions/0005). Notes carried forward: P3's equal-clock comparison should use the audited OR-Tools defaults; P5's selector should treat the budget as a feature (the best configuration changes between 1, 3 and 10 s); synthetic time-window instances are still missing (P5 generator).

The phases are done in order, but P4, P6 and P9 can run in parallel with the solver phases if the team splits work by person. Even with parallel work, the full must-have list needs roughly **7 to 9 calendar weeks**. That estimate is uncertain.

## Proposed cut line (depends on weeks remaining)
- **9 or more weeks:** all must-haves, plus one stretch item (customer tracking link).
- **6 to 8 weeks:** all must-haves, trimmed:
  - Solomon only (Gehring-Homberger dropped)
  - webhooks signed, but with simple retries
  - PWA photo upload kept small; offline cache limited to the stop list
  - copilot eval set of 50 instructions
- **4 to 5 weeks:** keep P1 (Solomon only), P2, P3, P5, P6 (no webhooks), P8 (tools: solve, compare, validate, reroute), and P4 with OSRM matrix plus fallback. Reduce P7 to breakdown + urgent order, and P9 to a stop list with delivered/failed marking (no photo, no offline). Write P10 as we go.
- **Under 4 weeks:** not realistic for the full title. Discuss with the mentor which features to promise.

Always kept, whatever the cut: the validator-first invariant, the stub notification adapter, honest labelling, and the old comparison as "Experimental Evaluation".

## Top risks
1. **Scope versus time.** Ten phases for three people. Mitigation: approve a cut line now; re-check pace after P1.
2. **Small local LLM reliability.** 3B to 8B models on laptop CPUs are slow and weaker at tool calling. Mitigation: schema-constrained JSON, Pydantic validation, one retry, then a clarifying question; fake LLM for tests; report results for the exact model only.
3. **Laptop setup.** Docker and Ollama are not installed on Rohit's laptop yet (checked 2 Nov 2026). OSRM preprocessing of a regional extract needs several GB of RAM, and Docker on Windows needs WSL2. Mitigation: set up early in P4; haversine fallback is flagged in the plan.
4. **GA with time windows.** Time windows make the split decoder harder, and GA quality may drop. Mitigation: penalty plus repair; the hybrid uses OR-Tools seeds; report negative results honestly.
5. **Timing fairness.** OR-Tools is not repeatable under a time limit, and laptops differ. Mitigation: repeats and seeds, one benchmark job at a time, record machine info, treat budget as a selector feature.
6. **No pilot data (unknown).** Mitigation: a clearly labelled realistic simulation if no operator data arrives.
7. **Python version.** This laptop has Python 3.14; the stack targets 3.12+. Some packages (LangChain, OR-Tools) may lag. Mitigation: pin versions in P1 and document in docs/decisions/.

## Deferred (do not build)
RAG over policy documents, demand forecasting, carbon estimation, a real SMS/WhatsApp provider.
