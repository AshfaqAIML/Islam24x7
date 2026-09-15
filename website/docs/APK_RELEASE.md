# APK Release — Islam24x7

The web app never assumes the APK lives in the same deployment. A release is
pure configuration — local file or any external CDN / GitHub Releases URL.

## Configure a release (`.env`)

| Variable | Example | Purpose |
|---|---|---|
| `APK_DOWNLOAD_URL` | `/downloads/islam24x7.apk` or `https://cdn.example.com/islam24x7-1.2.0.apk` | Artifact location |
| `APK_VERSION` | `1.2.0` | Surfaced on `/download` + first-visit prompt |
| `APK_RELEASE_DATE` | `2026-03-01` | ISO date |
| `APK_SIZE_LABEL` | `~18 MB` | Human label |
| `APK_MIN_ANDROID_VERSION` | `Android 8.0` | Minimum supported version |
| `APK_CHANGELOG` | `New Quran reader; faster search` | Comma/newline separated |

Leave `APK_DOWNLOAD_URL` unset → every surface shows the honest
“currently unavailable — continue on web” state. **The UI always tells the
truth about availability** (`/api/releases/latest` does a live fs/HEAD check).

## Local artifact

Drop the signed APK at:

```
public/downloads/islam24x7.apk
```

## Release checklist

1. Bump `APK_VERSION` / date / changelog in env.
2. Verify `GET /api/releases/latest` → `available: true`.
3. `/download` page shows the new version chips + working download button.
4. First-visit prompt (`?apkPrompt=auto` on desktop QA) reflects the same data.
5. `POST /api/downloads/track` increments (no PII stored).
