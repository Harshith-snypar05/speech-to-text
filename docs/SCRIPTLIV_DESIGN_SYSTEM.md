# ScriptLiv Design System

Source of truth: `stt/img_ref` mockups. This palette **supersedes** the brief's `#7C5CFF`.

## Tokens
| Token | Value |
|---|---|
| Primary | `#6A00FF` |
| Secondary | `#A855F7` |
| Accent | `#E9D5FF` |
| Background | `#F8F7FF` |
| Text | `#0F172A` |

Defined in `scriptliv_web/app/globals.css` (Tailwind v4 theme) and `st_transcribe_app/lib/theme.dart` (`AppColors`). A Flutter test asserts the three core values.

## Brand
Logo is a **vector redraw** of the reference, not the original artwork. Masters, PNG exports, Android and iOS `AppIcon.appiconset` are in `assets/branding/`.

## Web
Hand-written cva components (shadcn-style, not the shadcn CLI), framer-motion, lucide-react, Inter variable font.

## Flutter
Splash → 2 onboarding pages → sign in → shell with Home / Transcripts / Settings and centre mic button. Waveform widget is driven by real PCM RMS (`pcm16Rms`).

## Behavioural rules
- Partial text is visually distinct from final text; a partial is cleared when its final arrives and on stop.
- "Recording" state appears only after mic and WebSocket are both established.
- "Unavailable" is shown distinctly from zero for metrics. Client and server measurements are never combined.
- Pricing and unverified claims in the reference were omitted.
