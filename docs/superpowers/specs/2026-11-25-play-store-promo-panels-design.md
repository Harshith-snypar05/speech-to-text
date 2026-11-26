# Play Store promo panels: design (short)

Date: 2026-11-25. Status: awaiting approval.

## Intent and why
Replace raw app screenshots in the Play listing with designed promo panels that explain what ScriptLiv does, why it helps, and what is unique. This follows how other store listings work: each image carries one idea and a headline. Goal: a visitor swiping the listing understands the app without installing.

## Goals
- 6 portrait panels at 1080x1920 PNG (Play limits: 2 to 8, 9:16, max 8 MB each).
- Consistent with the existing feature graphic (`docs/play_store_assets/feature-graphic-1024x500.png`): dark purple, ScriptLiv logo, waveform motif.
- Palette `#6A00FF`, `#A855F7`, `#E9D5FF`, `#F8F7FF`, `#0F172A`; Inter font (`docs/SCRIPTLIV_DESIGN_SYSTEM.md`).
- Each panel: short headline, one-line support text, simplified app UI or illustration in a phone frame.

## Panels (proposal)
1. Words appear as you speak (live transcription).
2. Fixed a moment later (second accuracy model corrects lines in place). Hero panel, strongest visual.
3. Share a link, no sign-in (viewers follow live, free).
4. Understands Indian English accents.
5. History, search, export.
6. Meetings, lectures, conversations (who it helps).

## Non-goals / anti-goals
- No raw device screenshots.
- No "free 1000 minutes" panel: the offer ends 30 Nov, listing images outlive it.
- No claims the app does not back (check each against `docs/PLAY_STORE_RELEASE.md` section 5 and real behaviour).
- No billing, payment or promo changes; no store submission by me.

## Approaches considered
- A. HTML/CSS rendered to PNG with Playwright: fastest to iterate, but not what the user picked first.
- B. Flutter renders of real widgets inside panels: UI is exact, more setup per layout change.
- C. Figma: editable by a designer, export by hand.
- **Picked by user: C first; if Figma limits stop the work, move to B.**

## How it gets made
1. Create one Figma file "ScriptLiv Play Store panels" via the Figma MCP (`figma-use` and `figma-generate-design` skills). One 1080x1920 frame per panel, brand colours as variables, Inter, logo from `assets/branding/`.
2. Build the panels, then export PNGs at 1x to `docs/play_store_assets/panels/` (01 to 06).
3. Fallback trigger: Figma MCP returns a rate, quota, seat or plan limit, or cannot create or edit the file. Then I stop, report what was finished, and rebuild the remaining panels with B: a Flutter widget-test harness in `st_transcribe_app/test/` (not shipped in the app) rendering panel widgets to PNG via golden or `RepaintBoundary` capture. Figma frames already done are exported as they are, and B matches their look.
4. I do not touch `pubspec.lock`; any dependency B needs is avoided (use existing `flutter_test`).

## Left to the builder
Exact headline wording (kept to about 6 words), illustration details, phone frame style, and the simplified UI contents, within the palette above. Tell me any headline you want changed after the first render.

## Output and handoff
PNGs in `docs/play_store_assets/panels/`, left uncommitted. You upload them in Play Console, Main store listing, Phone screenshots. I cannot upload (Chrome tool is disconnected and has a 10 MB file limit).
