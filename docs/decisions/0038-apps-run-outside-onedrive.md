# 0038: start-dev.bat runs the console and driver app from a copy outside OneDrive

Date: 12 Nov 2026. Status: accepted (team chose option 1 of the clean-up list).

## Problem
CLAUDE.md says node_modules must stay outside OneDrive, but `start-dev.bat` (decision 0030) ran `npm install` in
`frontend\` and `driver\`. That put about 280 MB in about 27,000 files into OneDrive (150 MB and 131 MB by `du`),
which OneDrive kept syncing.

## Decision
- `start-dev.bat` mirrors `frontend\`, `driver\` and `design\` (the apps import `../design`) to
  `%LOCALAPPDATA%\LogiMind\` with `robocopy /MIR /XD node_modules dist` on every start, so the copy matches the
  repository and its own `node_modules` and `dist` are kept. `LOGIMIND_APPS` overrides the folder.
- `npm ci` runs in the copy when its `node_modules\.logimind-lock` is missing or differs from the repository's
  `package-lock.json`, so a changed lock file reinstalls the packages and an unchanged one starts at once.
- The console and driver windows run `npm run dev` in the copy. The API and worker still run from the repository.
- `--dry-run` prints the copy and `npm ci` steps and changes nothing.

## Consequences
- Editing the console or driver in the repository while it runs does not hot-reload. Run `start-dev.bat` again
  (or edit in the copy only for a quick try and then carry the change back). Accepted: the script is for demos and
  for trying the app; developers can still run `npm run dev` by hand outside OneDrive.
- The first start after this change runs `npm ci` twice (a few minutes, needs the network once).
- The repository's `frontend\node_modules` and `driver\node_modules` were deleted. `.gitignore` already covers them.
