# Deck draft: revised slides (Review 3)

DRAFT for the team, 5 Nov 2026. Written from PROMPT B in `docs/context/LogiMind_Kickoff_Prompts_ZeroCost.md`. **The .pptx was not edited.** Placeholders: [weeks remaining], [review dates]. Every number here comes from `docs/report/evaluation.md` or the committed result files; nothing is invented. Status words: **built** (code + passing tests), **verified** (also checked by hand in a browser), **not run / untested** (no evidence yet).

Notes for the slides NOT in this list:
- Keep the literature review slides (4-10) as they are.
- Old demo Results A and B (slides 22-23) are the SAME instance at two time budgets. New captions: "Same instance, [10 s or 3 s: confirm from the demo recording] budget". Keep both distance and cost on the slide (A: OR-Tools 246.29 km / 496.29 cost units vs GA 246.54 km / 496.54; B: OR-Tools 321.98 km / 571.98 vs GA 263.30 km / 513.30). Add: "single instance, single run: indicative only; see Experimental Evaluation". Move both under the heading "Experimental Evaluation (Review 2 comparison)".
- Slide 16 ("Proposed Solution") says the GA follows Zhu (2022). Our GA is our own design (giant tour + split, fleet repair, local search), not the Zhu design; correct or drop that sentence.

---

## Slide 1: Title
**Title:** LogiMind: An API-First Hybrid Optimization Platform with an AI Dispatch Copilot for Small-Fleet Logistics

**On slide**
- Capstone Project I (7CS1999), batch ASAC-CP-056, Review [review number]
- Rohit Raj, Pragya, Ishika; mentor Dr. M. Selvam
- Date of review: [review dates]

**Speaker notes (~60 s)**
Good morning. At Review 2 we showed a comparison of Google OR-Tools and our own genetic algorithm. The panel told us that a comparison alone is not enough for a capstone, and asked for a real system and a new title. LogiMind is that system. It is a route-planning platform for small delivery fleets: other software talks to it through an API, it combines exact-style and evolutionary solvers, and it has a dispatch copilot that understands plain language. Two rules shape everything we will show. First, the language model never makes routes: solvers make routes, and an independent validator checks every plan. Second, everything is zero cost and runs on our laptops. We will be clear about what is built, what is verified, and what is still planned.

**Diagram:** none (title slide).

---

## Slide 3: Project Overview
**Title:** Project Overview

**On slide**
- Problem: small fleets plan routes by hand or with tools that cannot explain or adapt
- LogiMind: plans routes with OR-Tools, our GA or a hybrid; picks the engine; replans after disruptions
- Dispatchers use a web console; drivers use a phone app (PWA); other systems use the REST API
- A copilot turns requests like "truck 1 broke down after two stops" into checked actions
- Zero cost: open-source solvers, local LLM (Ollama), self-hosted OSRM, simulated notifications

**Speaker notes (~60 s)**
Small couriers and distributors with five to fifty vehicles have the same routing problem as large companies, but not their budgets. LogiMind gives them three entry points. A dispatcher signs in to a web console, imports orders from a CSV or Excel file and gets a validated plan. A driver opens a signed link on a phone and marks stops delivered or failed, even offline. And any other system can do the same through the API with a key. When something goes wrong, a breakdown, a failed delivery or an urgent order, the plan is recomputed with the finished stops kept in place. The copilot is a convenience layer on top: it reads a request, asks back when unclear, asks for confirmation before changing a plan, and explains results using only the solvers' numbers. Customer notifications are simulated: they are logged, not sent, because we use no paid services.

**Diagram:** three users (dispatcher, driver, other system) -> LogiMind API -> solver engines + validator -> plan.

---

## Slide 11: Research Gap
**Title:** Research Gap

**On slide**
- Literature: OR-Tools and GAs each work well, but are studied separately, on different data
- Hybrids exist, but rarely with an honest equal-time comparison and ablations
- Solver selection is studied for algorithms, rarely inside a dispatch product
- LLM routing tools often let the model propose routes: no guarantee of feasibility
- **Gap:** no adaptive framework that combines hybrid optimization, solver selection and a safe LLM interface

**Speaker notes (~60 s)**
The papers we reviewed for Review 2 still stand. OR-Tools studies show guided local search and tabu search are strong; GA studies show good results on distribution and time-window problems. But they are tested one at a time, on different datasets and objectives. Hybrid methods appear, but usually without an equal-clock comparison, so we cannot tell whether the hybrid helps or just gets more time. Algorithm selection, choosing the solver per instance, is a research topic of its own, but it is rarely built into a planning product. And recent LLM routing demos often let the model write routes, which can break capacity or time windows. Our gap is the combination: an adaptive framework where solvers are compared fairly, a selector picks one per instance, and a language interface can only call validated tools.

**Diagram:** three overlapping circles (hybrid optimization, solver selection, LLM interface); LogiMind in the middle.

---

## Slide 12: Problem Statement
**Title:** Problem Statement

**On slide**
- Small fleets need routes that respect capacity and time windows, and change during the day
- Solver quality depends on the instance and the time budget: no single engine is best
- Dispatchers need plain-language control without risking invalid plans
- **Goal:** an API-first platform that chooses and runs the right engine, replans after disruptions, and offers a copilot that never generates routes
- Measured by: gap to best-known, runtime, constraint violations, replan time, selector regret

**Speaker notes (~60 s)**
Routing with capacities and time windows is hard, and it gets harder as the day goes on: trucks break down, customers are not home, urgent orders arrive. Our own measurements showed a second problem: which engine is best changes with the instance and the time budget. In our audit, the best OR-Tools setting changed between one, three and ten seconds; in our comparison, no engine won more than eighty percent of the cases. So the problem we solve is: build a platform that picks and runs a suitable engine, replans quickly while keeping finished stops fixed, and lets a dispatcher work in plain language without the language model ever touching the routes. We measure success with gap to published best-known solutions, runtime under an equal budget, constraint violations, time from disruption to a feasible plan, and the selector's regret.

**Diagram:** none, or a small loop: orders -> plan -> disruption -> replan.

---

## Slide 13: Objectives and Scope
**Title:** Objectives and Scope

**On slide**
- O1 Common model: CVRP with time windows; independent validator *(built)*
- O2 Engines: OR-Tools (audited), own GA, hybrid; equal-clock evaluation *(built; evaluated)*
- O3 Engine picker with explanation *(built; synthetic data; not a proven gain)*
- O4 Platform: API keys, tenants, import, job queue, webhooks, replanning *(built)*
- O5 Copilot on a local LLM; driver PWA; simulated ETA messages *(built; real-model evaluation not run)*
- O6 Road distances (self-hosted OSRM) with flagged fallback *(built; OSRM not run yet)*
- Design rule: **the LLM never generates routes; solvers are the source of truth**
- Deferred: RAG over policies, demand forecasting, carbon estimation

**Speaker notes (~60 s)**
We have six objectives. The first two are the foundation: one problem model with time windows, and three engines compared under the same clock. The third is an engine picker that explains its choice. Four is the platform itself: tenants with API keys, order import, a durable job queue with a separate worker, webhooks and replanning. Five covers the people: a copilot on a local open-source model, a driver app that works offline, and ETA messages that are simulated. Six is real road distances from a self-hosted OSRM server, with a clearly flagged fallback. Each objective shows its status. The design rule is on the slide because it is the core safety idea: the language model never generates routes. Three things are deliberately out of scope: retrieval over policy documents, demand forecasting and carbon estimation.

**Diagram:** none (status tags in brackets).

---

## Slide 15: Methodology
**Title:** Methodology

**On slide**
- Instances: Solomon VRPTW and CVRPLIB CVRP (published best-known values, source and date recorded) + labelled synthetic instances
- Engines get the same instance, matrix, objective and TOTAL time budget; runs one at a time
- Every plan -> independent validator -> metrics (gap, runtime, violations)
- Held-out evaluation: 24 instances never used for tuning, 3 repeats, Wilcoxon signed-rank + Holm
- Selector: features -> dataset -> grouped cross-validation -> regret vs baselines
- Copilot: intents in a fixed schema; tools return numbers; replies only quote tool numbers

**Speaker notes (~60 s)**
Our method is built around fairness and evidence. We use the standard Solomon and CVRPLIB benchmark sets, because they have published best-known solutions; we record where and when we took each value. Every engine gets the same instance, the same distance matrix, the same objective and the same total time, including any set-up, and runs are executed one at a time. Every plan goes through an independent validator, so a solver cannot grade itself. For the final evaluation we added twenty-four instances that were never used to tune anything, ran three repeats per engine, and tested differences across instances with the Wilcoxon signed-rank test and a Holm correction. The selector is trained on generated instances and checked with cross-validation that holds out whole families. The copilot is evaluated separately on a fixed instruction set, once a real model is installed.

**Diagram:** pipeline: instances -> (OR-Tools | GA | hybrid) -> validator -> metrics -> statistics; selector feeding the engine choice.

---

## Slide 17: Architecture
**Title:** System Architecture

**On slide**
- Clients: ops console (React), driver PWA, other systems (REST + API key)
- FastAPI: auth and rate limit, plans, import, replan, webhooks, audit, copilot, driver
- Database job queue -> worker process -> guarded solver process (hard timeout)
- Engines: OR-Tools, GA, hybrid; picker; distances (OSRM or flagged fallback)
- Independent validator decides "feasible"; tenant isolation in the data layer
- **The LLM never generates routes; solvers are the source of truth**

**Speaker notes (~60 s)**
Here is how a request flows. A client calls the API. The API checks the key, stores the plan and a job in one database transaction, and returns at once. A separate worker process claims the job, builds the distance matrix, and runs the chosen engine inside a guarded process that is killed if it runs too long; a timeout is stored as a timeout, never as a success. The routes go to the independent validator, and only the validator decides whether a plan is feasible. Then the plan is updated and webhooks are sent. If a worker crashes, another worker picks the job up again after thirty seconds; we tested this by killing a real worker in the middle of a job. Every query for a tenant is filtered by tenant in the data layer. The copilot sits beside the API: its model can only choose a tool and fill a checked form; it cannot write a route.

**Diagram:** the block diagram from `docs/architecture.md` (clients -> API -> database/job queue -> worker -> guarded solver -> validator; copilot -> tools -> API).

---

## Slide 18: Timeline (work done)
**Title:** Work Plan: Done So Far

**On slide**
- P1 time windows + benchmarks; P2 OR-Tools audit (1728 runs); P3 hybrid + equal-clock comparison
- P5 engine picker; P6 platform + job queue; P7 replanning; P8 copilot; P9 driver PWA + notifications
- P4 road distances: built, tested offline; P10 evaluation report: first version
- Not yet: Docker Compose run, OSRM run, real-model copilot evaluation, phone test

**Speaker notes (~60 s)**
This slide shows what is done. We split the work into ten phases. Phases one to three gave us time windows, public benchmarks, an audit of OR-Tools settings with seventeen hundred and twenty-eight runs, and the hybrid with a fair comparison. Phases five to nine built the platform: the engine picker, tenants and the API, the job queue, replanning, the copilot, the driver app and simulated notifications. Phase four, road distances, is built and tested with recorded answers, but we have not run our own OSRM server yet. Phase ten, the evaluation, has a first report. The last line is honest about the gaps: Docker is not installed on our development laptop yet, the copilot has not been tested with a real model, and the driver app has not been tried on a phone.

**Diagram:** a horizontal bar of P1-P10, done phases filled, partial ones hatched.

---

## Slide 19: Timeline (remaining work and cut line)
**Title:** Work Plan: Remaining [weeks remaining] Weeks

**On slide**
- Week 1: Docker Compose + PostgreSQL run; self-hosted OSRM on a Bengaluru extract
- Week 2: install Ollama; freeze the 50-item copilot set; measure the real model
- Week 3: phone test of the driver app; 10 s held-out runs; final report and deck
- Reviews: [review dates]
- **Cut line** if time is short: keep validator, honest labels, stub notifications; drop OSRM run before copilot evaluation

**Speaker notes (~60 s)**
With [weeks remaining] weeks left, the plan is three short blocks. First, run what is written but untested: the Docker Compose stack with PostgreSQL, and our own OSRM server on a map extract of Bengaluru. Second, install Ollama, freeze the copilot instruction set with the team, and measure how often the model picks the right intent. We will report that number for the exact model only. Third, test the driver app on a real phone and run the longer ten-second benchmark on the held-out instances, then finish the report and slides. If time runs short, the cut line on the slide decides what goes first. Some things are never cut: the validator-first rule, honest labelling of synthetic and simulated parts, and the stub notifications. Our review dates are [review dates].

**Diagram:** three blocks on a timeline with [review dates] markers; a dashed cut line.

---

## Slide 24: Conclusion
**Title:** Conclusion

**On slide**
- LogiMind turns a solver comparison into a working, API-first planning platform
- Plans are always validated; failures, timeouts and fallbacks are shown as such
- 24 held-out benchmarks, 3 s: GA+LS beats OR-Tools on CVRP (10 of 12); OR-Tools beats GA+LS on VRPTW (12 of 12); hybrid not significantly different from OR-Tools
- Negative results kept: hybrid not a clear win; engine picker not a proven gain
- Next: real-model copilot evaluation, OSRM run, Docker deployment, phone test

**Speaker notes (~60 s)**
To conclude: we took the Review 2 comparison and built it into a platform. Dispatchers can import orders, get a validated plan, replan after a disruption, and send drivers a link to their route. Every plan passes an independent validator, and anything that fails, times out or falls back to straight-line distances says so. On twenty-four benchmark instances that were never used for tuning, with three seconds per run, our GA with local search had a smaller gap than OR-Tools on ten of twelve capacity-only instances, which is just significant after correction, while OR-Tools was better on all twelve time-window instances. The hybrid was not significantly different from OR-Tools. We also report what did not work: the hybrid is not a clear improvement over OR-Tools with its current settings, and our engine picker, trained on synthetic data, is not proven better than always using the hybrid. Next we will measure the copilot with a real local model, run our own OSRM, deploy with Docker, and test the driver app on a phone. Thank you.

**Diagram:** none.
