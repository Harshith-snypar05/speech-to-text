# Publishing ScriptLiv on Google Play

Status 2026-11-19: signing is set up, a signed `.aab` builds, and build 1.0.0+1 passed an internal test on a real phone. Build 1.0.0+2 adds the 1000-minutes-per-user offer rule (no plans shown). What is left is the Play Console forms, a closed test if the account needs one, and review.

## 1. Before you build

1. **Production server is live** with https for the API and wss for the relay (see `PRODUCTION_RUNBOOK.md`). The app has no server address inside it; you pass it at build time.
2. **Offer env** is set on the API: `SCRIPTLIV_PROMO_UNLIMITED_UNTIL=2026-11-30`.
3. **Upload keystore** exists at `C:\Users\sriha\snypar\stt\keys\scriptliv-upload.jks`, with `st_transcribe_app\android\key.properties` pointing to it (git-ignored). **Back both up now** (password manager plus a second copy). If the upload key is lost, Play support can reset it, but it takes days.
   - To make a new keystore on another machine: `keytool -genkeypair -v -keystore scriptliv-upload.jks -storetype PKCS12 -alias upload -keyalg RSA -keysize 2048 -validity 10000`, then create `android/key.properties` with `storePassword`, `keyPassword`, `keyAlias=upload`, `storeFile=<path with forward slashes>`.

## 2. Build the bundle

From `st_transcribe_app`:

```
flutter build appbundle --release ^
  --dart-define=SL_API_HTTP=https://YOUR-API-DOMAIN ^
  --dart-define=SL_WS=wss://YOUR-RELAY-DOMAIN
```

Output: `build\app\outputs\bundle\release\app-release.aab`. Raise the build number in `pubspec.yaml` (`version: 1.0.0+2`) for every new upload; Play refuses a repeated number.

The tool prints "failed to strip debug symbols". The bundle is still produced and signed. To fix it, install "Android SDK Command-line Tools" in Android Studio (SDK Manager) and run `flutter doctor --android-licenses`.

Before uploading, install a release build on a real phone (`flutter build apk --release` with the same defines) and test sign-up, email verification, a live session, the web share link and account deletion.

## 3. Play Console, one time

1. **Create app**: name ScriptLiv, default language English (India), App, Free, accept the declarations.
2. **App signing**: choose "Play App Signing" (default). The first upload of the `.aab` registers your upload key.
3. **Set up your app** (Dashboard checklist):
   - **Privacy policy**: public URL, e.g. `https://YOUR-DOMAIN/privacy`.
   - **App access**: "All or some functionality is restricted". Add a test account (email and password) that is already verified, and say how to start a session (tap the mic).
   - **Ads**: No.
   - **Content rating**: questionnaire, category "Utility, productivity". No violence and so on; expect Everyone/3+.
   - **Target audience**: 18 and over.
   - **News app / Government / Health / Financial features**: No.
   - **Data safety** (below).
   - **Account deletion**: the app deletes in Settings. Also give the web URL `https://YOUR-DOMAIN/app/settings`.
4. **Store listing** (below). Needs: 512x512 icon, 1024x500 feature graphic, 2 to 8 phone screenshots (at least 2; 1080x1920 or similar). Capture them from the release build; `docs/screenshots` may hold usable ones.
5. **Pricing and distribution**: Free, select countries (India first is fine).

## 4. Data safety answers

The app collects and sends to the server:

| Data | Collected | Shared with third parties | Purpose | Optional |
|---|---|---|---|---|
| Email, name | Yes | No | Account management | No |
| Phone (if given at checkout) | Yes | Payment provider (Cashfree) | Payments | Yes |
| Audio | Yes, processed live; not stored as a recording | No | App functionality | No (core feature) |
| Transcripts (text of what was said) | Yes, stored | Only if the user turns on a share link | App functionality | No |
| Payment info | Handled by Cashfree, not stored by ScriptLiv | Cashfree | Payments | Yes |

Also: data encrypted in transit (yes); users can request deletion (yes). Check this table against the real behaviour and `privacy` page before you submit; Google compares them.

## 5. Store listing text (draft)

- **App name**: ScriptLiv: Live Speech to Text
- **Short description (80)**: Live transcription for meetings, lectures and conversations. Share it as it happens.
- **Full description**:
  ScriptLiv turns speech into text while people are still talking. Open the app, tap the mic, and words appear instantly. A moment later each line is re-checked by a second, more accurate model and corrected in place, which helps with Indian English accents.

  - Live transcription as you speak
  - Accuracy pass that fixes lines after they appear
  - Share a link so others can follow the transcript live, no sign-in needed
  - History, search and export of past sessions
  - Free during our launch offer: 1000 minutes per user

  Needs the microphone and an internet connection. Only the person speaking uses minutes; people watching a shared link are free.

## 6. Release path

1. Create an **Internal testing** release first, upload the `.aab`, add yourself and teammates as testers, install from the Play link and test.
2. **New personal developer accounts** (created after Nov 2023) must run a **Closed test with at least 12 testers for 14 continuous days** before they can apply for production. Organisation accounts do not. Check your account type under Dashboard.
3. Then **Production**: create the release, add notes ("First release"), roll out. Review usually takes from a few hours to a few days; the first app can take longer.

## 7. After the offer (30 Nov)

If the app lets people buy minutes after the offer, Google requires **Play Billing** for digital goods sold inside an Android app. During the offer the app shows no plan or "Manage plan" link (1.0.0+2). The app has no purchase screen; after the offer "Manage plan" opens the website. Decide before 30 Nov: keep purchases on the website only and remove the link from the app (so the app never points users to external payment), or add Play Billing. Not decided yet.

## 8. Known limits to tell reviewers and testers

- The app listens through the phone microphone only. It cannot record phone or WhatsApp call audio (Android blocks it); speakerphone near the mic is the only way.
- Keeping listening with the screen off needs a foreground service. Not built yet.
