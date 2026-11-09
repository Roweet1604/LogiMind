# UI screenshots: "Freight Yard" theme (decision 0027)

Taken on 10 Nov 2026 with real Chrome (Google Chrome on this laptop, headless, separate profile, driven by a
puppeteer-core script kept outside the repository) against a local backend on a temporary SQLite database:
research endpoints off, OSRM pointed at a closed port (so the fallback warning is real), Ollama not installed
(so the copilot's "no local model" state is real). **The tenant, orders and plans are all synthetic.**

Desktop shots are 1440 × 900. "390px" shots use a 390 × 844 viewport at 2× with touch emulation (Chrome device
emulation, not a real phone). The offline shots used Chrome's own offline mode (network switched off for the page).

| File | What it shows |
| --- | --- |
| 01-console-sign-in.png | Sign-in page (signed out): yellow active nav item, condensed uppercase heading, ink rule under the header |
| 02-console-plans-list.png | Plans list: validator badges (no plan = red, feasible = green on white with an ink border), engine line styles, dashed "synthetic" labels, "urgent order" replan label |
| 03-console-plan-fallback-warning.png | Plan view: status strip (feasible, hybrid, fallback estimate) and the dark fallback warning above the map and route list |
| 04-console-plan-with-copilot-dock.png | Same plan with the copilot docked ("no local model"); the map keeps the full width and the route list moves below it |
| 05-console-plan-replanned.png | A replanned plan: "replanned" label with a link to the parent plan; OR-Tools solid blue lines |
| 06-console-plan-drivers-and-replan-form.png | Lower half of a plan: Drivers panel and the replan form (displayed, not submitted) |
| 07-console-plan-hybrid-planar.png | A hybrid plan on planar coordinates: dash-dot grey lines |
| 08-console-plan-no-solution.png | A plan with no solution (one van, two far-apart deadlines): red "no plan", "No solution found" |
| 09-console-copilot-no-model.png | Copilot page: the "no local model" error and the disabled input |
| 10-console-research-page-switched-off.png | A research page with the dark "switched off" banner |
| 11-console-keyboard-focus-sidebar.png | Keyboard focus (Tab) on the dark sidebar: yellow 2px ring |
| 12-console-plan-390px.png | Plan view at 390 px: no horizontal scroll |
| 13-driver-stop-list-390px.png | Driver app: dark header, Online, progress, 64 px buttons, the next stop's yellow Navigate |
| 14-driver-failed-reason-390px.png | Failed form with a reason chosen (not submitted) |
| 15-driver-offline-queued-390px.png | Chrome offline: "Offline", saved copy banner, "1 update waiting to sync", Sync now |
| 16-driver-back-online-synced-390px.png | Network back: the app synced the queued report by itself and shows Online |
| 17-driver-link-invalid-390px.png | A link with a tampered signature: "Link no longer valid" |
