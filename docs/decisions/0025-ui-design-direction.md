# 0025: UI design direction (ops console and driver app)

Date: 10 Nov 2026. Status: accepted (decided unattended by Claude Code, branch `ui-redesign`).

## Direction (8 lines)
1. Tone: a calm, precise dispatch control room and engineering tool; no marketing look, no chat-app look.
2. Palette: warm paper background, white working surfaces, charcoal text, ONE teal accent used only for actions and focus; no gradients, glass, glow, blobs or emoji.
3. Engines keep fixed line styles: OR-Tools solid blue, GA dashed orange, hybrid dash-dot slate (its own colour and pattern, always labelled "Hybrid").
4. Status is semantic and never colour alone: every status has an icon and a word (feasible, infeasible, timeout, fallback distances, replanned, draft/synthetic, queued/running, failed).
5. Type: Inter (self-hosted via npm) with JetBrains Mono for ids; tabular numbers for distances, times and costs; compact tables with right-aligned numbers.
6. Plan view: the validator verdict and any fallback or timeout warning sit in a status strip at the top; the map is the centre with the route list beside it; forms come after.
7. Navigation: a fixed left rail with the existing sections; the copilot is a docked right panel (model status, tool results used, Confirm/Cancel) that can be opened from any page.
8. Driver app: mobile-first, one-thumb, targets at least 56 px, high contrast for sunlight, a full-width Navigate button for the next stop, and a sticky Online/Offline and sync bar.

## Implementation notes
- Colours, spacing, radii and type sizes live in one file, `design/tokens.js`; both `tailwind.config.js` files and the engine line styles (`frontend/src/lib/algos.js`) read it.
- Because the tokens are outside the app folders, the Docker build context for `console` and `driver` is now the repository root (`docker-compose.yml`, both Dockerfiles). Still UNTESTED (no Docker, decision 0020).
- Contrast (WCAG 2.1, measured with a script): every text pair is at least 4.5:1 (lowest: warning text 4.80:1). The GA orange line is 4.09:1 on white, used for lines only (3:1 needed); GA text uses the darker `ga.text` (5.35:1 on its tint).
- Found in the browser check and changed (display only):
  - The map no longer zooms on the mouse wheel. With a large map in the middle of the page, the wheel zoomed the map instead of scrolling the page. Zoom is now the +/− buttons, double-click or pinch.
  - Driver header: when the phone has a network but the server does not answer (e.g. a 5xx from a proxy), the app already showed the saved copy, but the badge said "Online". It now says "Server unreachable". The sync and retry logic is unchanged.
  - Focus ring on dark surfaces uses the teal tint (14.6:1); plain teal there was 2.9:1.
- Behaviour is unchanged: API-key handling, validator display, replan Confirm/Cancel, offline sync and tenant behaviour are the same code paths; only markup and styling moved.
