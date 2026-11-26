# Play Store Promo Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce 6 designed 1080x1920 promo PNGs for the ScriptLiv Play listing, built in Figma, with a Flutter fallback if Figma limits stop the work.

**Architecture:** One Figma file, one 1080x1920 frame per panel, brand colours as Figma variables, shared panel layout (headline, support line, phone frame with simplified UI). Frames export to PNG. Fallback B renders the same layouts as Flutter widgets in a test harness.

**Tech Stack:** Figma MCP (`use_figma`, skills `figma:figma-use`, `figma:figma-generate-design`), Inter, Flutter `flutter_test` (fallback only).

**Spec:** `docs/superpowers/specs/2026-11-25-play-store-promo-panels-design.md`

## Global Constraints

- Frame size 1080x1920, PNG, under 8 MB each; 6 panels named `01-live.png` to `06-who.png`.
- Palette: `#6A00FF`, `#A855F7`, `#E9D5FF`, `#F8F7FF`, `#0F172A`; dark panel base matches `docs/play_store_assets/feature-graphic-1024x500.png`.
- Font Inter. Headline at most 6 words.
- No raw device screenshots. No free-offer or minutes panel (offer ends 30 Nov).
- Only claims in `docs/PLAY_STORE_RELEASE.md` section 5.
- Do not touch `pubspec.lock`. No commit, push, or Play upload unless the user asks.
- Output dir `docs/play_store_assets/panels/`.

## Review Focus

- Headline wraps to 3+ lines or overflows the frame: it must stay inside 80px side margins and 160px top and bottom safe zones.
- Support text low contrast on purple: body text must be at least 4.5:1 against its background.
- Inter missing in the Figma file: text falls back to another font; check font names before export.
- Export at wrong scale (2x gives 2160x3840): files must be exactly 1080x1920.
- Panel claim stronger than the product (e.g. "100% accurate"): wording must match the store description.

## File Structure

- Figma file "ScriptLiv Play Store panels": page "Panels", frames `01` to `06`, page "Foundations" for variables and logo.
- `docs/play_store_assets/panels/*.png`: exports.
- Fallback only: `st_transcribe_app/test/promo/panel_render_test.dart` and `st_transcribe_app/test/promo/panels.dart`.

---

### Task 1: Figma file and foundations

**Files:** Figma file (new). Logo source: wordmark PNG or SVG under `assets/branding/` (list the directory, pick the horizontal wordmark).

**Interfaces:**
- Produces: Figma file URL; variables `brand/primary`, `brand/secondary`, `brand/accent`, `brand/bg`, `brand/text`, `panel/dark`; a component `PanelBase` (1080x1920, dark gradient from `panel/dark`, waveform motif bottom, logo top-left).

- [ ] **Step 1:** Run `whoami`; if not authenticated, authenticate and stop for the user to complete login. Load `figma:figma-use` before any `use_figma` call.
- [ ] **Step 2:** Create the file "ScriptLiv Play Store panels" (`figma:figma-create-new-file`).
- [ ] **Step 3:** Create the colour variables with the exact hex values above, with `panel/dark` sampled from the feature graphic (read the PNG).
- [ ] **Step 4:** Build `PanelBase` with the logo imported from `assets/branding/`.
- [ ] **Step 5:** Verify: screenshot the frame; logo visible, no clipped waveform. Expected: matches the feature graphic's look.

### Task 2: Panels 01 to 03

**Interfaces:**
- Consumes: `PanelBase`, variables from Task 1.
- Produces: frames `01 Live`, `02 Fixed`, `03 Share`, each with headline (Inter Bold, 96px, `brand/bg`), support line (Inter Regular, 44px, `brand/accent`), and a phone frame holding simplified UI.

Copy (exact):
- 01: "Words appear as you speak" / "Live transcription, instantly."
- 02: "Fixed a moment later" / "A second, more accurate check corrects each line in place."
- 03: "Share a link. No sign-in." / "Anyone can follow the transcript live."

- [ ] **Step 1:** Build frame 01: phone UI shows a transcript growing line by line with a mic button.
- [ ] **Step 2:** Build frame 02 (hero): same line shown twice in the phone, a wrong word struck through and the corrected word highlighted in `brand/secondary` with a check mark.
- [ ] **Step 3:** Build frame 03: a phone sharing a link chip, and a second smaller phone or browser tile showing the same live text.
- [ ] **Step 4:** Verify each frame by screenshot: text inside safe zones, contrast readable, Inter applied (check font name on text nodes).

### Task 3: Panels 04 to 06

**Interfaces:**
- Consumes: as Task 2.
- Produces: frames `04 Accents`, `05 History`, `06 Who`.

Copy (exact):
- 04: "Understands Indian English" / "Built to follow real accents."
- 05: "History, search, export" / "Every session saved and ready to share."
- 06: "For meetings, lectures, talks" / "Live words for every conversation."

- [ ] **Step 1:** Frame 04: phone with a transcript plus a stylised accent waveform; no flags or maps.
- [ ] **Step 2:** Frame 05: phone with a session list, a search field, an export button.
- [ ] **Step 3:** Frame 06: three simple scene icons (meeting, lecture, conversation) around the logo.
- [ ] **Step 4:** Verify each by screenshot, same checks as Task 2.

### Task 4: Export and check

**Files:** Create `docs/play_store_assets/panels/01-live.png`, `02-fixed.png`, `03-share.png`, `04-accents.png`, `05-history.png`, `06-who.png`.

- [ ] **Step 1:** Export each frame as PNG at 1x via the Figma MCP asset download.
- [ ] **Step 2:** Run in Bash: `file docs/play_store_assets/panels/*.png`. Expected: each reports `1080 x 1920`.
- [ ] **Step 3:** Run `ls -l docs/play_store_assets/panels`. Expected: each under 8 MB.
- [ ] **Step 4:** View each PNG with the Read tool for a final visual check; fix and re-export any with clipped text.
- [ ] **Step 5:** Report to the user: paths, Figma URL, and that upload is manual (Play Console, Main store listing, Phone screenshots).

### Task 5 (only if Figma limits hit): Flutter fallback

**Trigger:** any Figma MCP call returns a rate, quota, seat or plan limit, or cannot create or edit the file. Stop, report which panels are finished and exported.

**Files:** Create `st_transcribe_app/test/promo/panels.dart`, `st_transcribe_app/test/promo/panel_render_test.dart`.

**Interfaces:**
- Produces: `Widget buildPanel(PanelSpec spec)` where `PanelSpec` has `String headline`, `String support`, `Widget phoneContent`; a test `renders promo panels to PNG` that writes 1080x1920 PNGs to `docs/play_store_assets/panels/` via `RepaintBoundary.toImage(pixelRatio: 1)`.

- [ ] **Step 1:** Write the test asserting each rendered image is 1080 wide and 1920 high; run `flutter test test/promo/panel_render_test.dart`; expect FAIL (no widget yet).
- [ ] **Step 2:** Implement `buildPanel` using the palette and the Inter font bundled in `st_transcribe_app/assets/fonts`, for only the panels not yet exported from Figma, same copy as Tasks 2 and 3.
- [ ] **Step 3:** Run the test; expect PASS and PNGs written.
- [ ] **Step 4:** Run `git checkout -- st_transcribe_app/pubspec.lock` if it changed; confirm `git status` shows no `pubspec.lock` change.
- [ ] **Step 5:** Repeat Task 4 steps 2 to 5 for the new PNGs.

---

## Self-review

- Spec coverage: panels, palette, no-offer, Figma-first with fallback trigger, output dir, no commit or upload: all covered.
- Types: `PanelBase` and variable names are the same in Tasks 1 to 3; `buildPanel` and `PanelSpec` are defined only in Task 5.
- Review Focus lines are covered by the verify steps in Tasks 2 to 4 (safe zone, contrast, font name, 1080x1920 check, claim wording).
