# UI screenshots (redesign, decision 0025)

Taken on 10 Nov 2026 in desktop Chrome (Claude in Chrome extension) against a local backend on a temporary SQLite
database: research endpoints off, OSRM pointed at a closed port (so the fallback warning is real), Ollama not
installed (so the copilot's "no local model" state is real). **All orders, plans and the tenant are synthetic.**

The Chrome window was zoomed out (viewport about 2304 CSS px wide), so the desktop shots show the 1600 px content cap.
"390px" shots are the real app loaded in a 390 px wide same-origin iframe, not a phone and not device emulation.

| File | What it shows |
| --- | --- |
| 01-console-plans-list.jpg | Plans list: validator badges (icon + word), engine line styles, "synthetic" and "urgent order" replan labels, right-aligned numbers |
| 02-console-plan-fallback-with-copilot-dock.jpg | Plan view: status strip (validator, engine, fallback distances), fallback warning, map beside the route list, copilot docked with "no local model" |
| 03-console-plan-replanned.jpg | A replanned plan: "replanned" flag with a link to the parent plan; OR-Tools solid blue routes |
| 04-console-plan-drivers-and-replan.jpg | Lower half of a plan: engine and replan notes, Drivers panel, replan form (taken before the Drivers table columns were narrowed) |
| 05-console-plan-hybrid-planar.jpg | A hybrid plan on planar coordinates: dash-dot slate lines, its own style |
| 06-console-copilot-no-model.jpg | Copilot page: model status, the "no local model" message, input disabled |
| 07-console-signed-out-empty-state.jpg | Signed-out empty state |
| 08-console-research-page-switched-off.jpg | A research page with the "switched off on this backend" banner |
| 09-console-plan-390px.png | Plan view at 390 px: nav scrolls sideways, status strip wraps, no horizontal page scroll |
| 10-console-copilot-dock-390px.png | Copilot dock at 390 px: full screen with a close button (still checking for a model) |
| 11-driver-stop-list-390px.png | Driver app: Online, progress, next stop with the 64 px Navigate / Delivered / Failed |
| 12-driver-failed-reason-390px.png | Failed form with a reason chosen (not submitted) |
| 13-driver-server-unreachable-queued-390px.png | API stopped: "Server unreachable", saved copy banner, "1 update waiting to sync", Sync now |
| 14-driver-after-sync-now-390px.png | API restarted, Sync now pressed: back to Online, both stops Delivered, queue empty |
| 15-driver-link-expired-390px.png | API restarted without a fixed link secret: link invalid, the unsent report is mentioned |
