# 0027: "Freight Yard" theme (replaces the colours and type of 0025)

Date: 10 Nov 2026. Status: accepted (theme given by the team; applied unattended by Claude Code on `ui-redesign`).
Decision 0025 still holds for layout, status rules and behaviour; this record replaces its palette, fonts and radii.

## Direction
- Concrete-grey page (#EDEDEA), white panels, #CFCFCA borders, ink text (#1A1A1A), muted #55554F; a 2px ink rule under each page header.
- One accent, safety yellow #FFC400. On light surfaces it is only a BACKGROUND, always with ink text (primary buttons, the active nav item, the selected tab or route, the driver's main action). Yellow text or icons appear only on dark surfaces (sidebar brand, driver header, warning badges).
- Sidebar and driver header: #1A1A1A with #D6D6D0 text; the active item is yellow with ink text; the brand name is yellow.
- Buttons: primary = yellow + bold ink text; secondary = transparent with a 1px ink border (`btn-on-dark` uses a light border on dark blocks).
- 4px corners everywhere (including former pills); no gradients, glow or glass; shadows removed (hairline borders only).
- Type, bundled from npm (OFL-1.1, nothing loaded from the internet): headings Barlow Condensed 700, uppercase, 0.04em tracking; body IBM Plex Sans 400–700; JetBrains Mono for ids; tabular numbers.
- Engine lines unchanged in meaning, new exact values: OR-Tools solid #1D4ED8, GA dashed #C2410C, hybrid dash-dot #57606A. Yellow is never a data line (tested).
- Status (icon + word, never colour alone): feasible = green #166534 on white with an ink border; warning (fallback distances) and draft/synthetic/preliminary (dashed) = yellow on #1A1A1A; infeasible, failed and timeout = white on solid red #B42318 (timeout has a clock icon); error notices = red edge on a light red tint.
- Map: background #E2E2DD, depot #1A1A1A. OSM raster tiles are shown in greyscale (CSS filter); raster tiles cannot be recoloured exactly, so roads come out light grey near #C9C9C3 rather than exactly that colour.
- Driver app: same palette, light page for sunlight, dark header; Navigate / Delivered / Failed are 64px on every stop; the next stop's Navigate is the yellow main action; Delivered is solid green, Failed is red-outlined.
- Focus ring: 2px (console) / 3px (driver) ink on light surfaces, yellow on dark ones (ink on the sidebar would be invisible).
- PWA icons regenerated (yellow square, ink "L") by `driver/scripts/make-icons.mjs`; manifest colours read the tokens.

## Contrast pairs checked (WCAG 2.1; 4.5:1 needed for normal text). Enforced by `frontend/src/test/design.test.jsx`.
| Pair | Ratio |
| --- | --- |
| text #1A1A1A on page #EDEDEA / panel #FFFFFF | 14.84 / 17.40 |
| muted #55554F on page / panel / table head #F6F6F3 | 6.40 / 7.50 / 6.93 |
| ink on yellow #FFC400 (primary button, active nav) / on hover #E5B000 / on yellow tint #FFF1BF | 10.90 / 8.74 / 15.40 |
| nav text #D6D6D0 / nav muted #A3A39B / yellow brand on #1A1A1A | 11.93 / 6.85 / 10.90 |
| feasible #166534 on white | 7.13 |
| warning yellow on #1A1A1A / warning body #EDEDEA on #1A1A1A | 10.90 / 14.84 |
| white on red #B42318 (infeasible, timeout, failed) / red text on white | 6.57 / 6.57 |
| error title #8F1D14 on tint #FDECEA / ink on that tint | 7.80 / 15.22 |
| ink on ok tint #EEF5EF / white on green (Delivered) | 15.70 / 7.13 |
| OR-Tools label / GA label #9A3412 / hybrid label on white | 6.70 / 7.31 / 6.39 |
| Lines on the map background (3:1 needed): OR-Tools / GA / hybrid | 5.16 / 3.98 / 4.92 |
| Not allowed, for reference: yellow text on white / on page | 1.60 / 1.36 |
