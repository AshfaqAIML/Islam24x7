# Android — Islam24x7

One codebase. The Android app is a **Capacitor wrapper around the production
web build** — no second implementation of any screen (§25).

## Status

Planned for **Phase 13** of `ARCHITECTURE.md`. The web side of the Android
experience is already live: config-driven release metadata, `/download`
install page, first-visit prompt with persistent dismissal, and QA overrides
(`?apkPrompt=1|auto|0`).

## Provisional identifiers (document as provisional — do not ship blindly)

| Item | Value (provisional) |
|---|---|
| App name / label | `Islam24x7` |
| Package id | `app.islam24x7.mobile` |
| Splash | Brand emerald + eight-pointed-star mark |
| Icon | `public/icons/icon-512.png` master |

Change these in `capacitor.config.ts` once the shell is created — the web
app reads the name from `src/config/brand.ts` only.

## Planned build process (Phase 13)

```bash
bun run build:web              # production web build
bun run build:android          # Capacitor sync + debug APK
bun run build:android:release  # signed release APK
```

- Signing keys come from env vars (`ANDROID_KEYSTORE_PATH`,
  `ANDROID_KEYSTORE_PASSWORD`, `ANDROID_KEY_ALIAS`, `ANDROID_KEY_PASSWORD`).
  **Never commit keystores or passwords.**
- Output: `android/app/build/outputs/apk/…` → copied to
  `public/downloads/islamic-knowledge.apk` or uploaded to a CDN
  (then set `APK_DOWNLOAD_URL`).

## Device behavior (live today)

| Platform | First visit | Notes |
|---|---|---|
| Android | Elegant APK prompt → Download / Continue on web / Not now | Dismissal persists; download silences auto-prompts |
| iOS | No APK option | Never shows misleading instructions |
| Desktop | No prompt; optional “Get the App” CTA in header | — |
