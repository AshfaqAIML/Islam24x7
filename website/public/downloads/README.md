# APK release artifact location

Place the signed release APK here as `islamic-knowledge.apk`, or point
`APK_DOWNLOAD_URL` (see `.env.example`) at any external host:

- local:      `/downloads/islamic-knowledge.apk`  (this folder)
- CDN/GitHub: `https://…/islamic-knowledge-1.0.0.apk`

The `/download` page and the first-visit Android prompt check availability
live (via `GET /api/releases/latest`) and degrade gracefully when no artifact
is published — they never trap the user.

Build & release process: see `docs/ANDROID.md` and `docs/APK_RELEASE.md`
(added in the Android packaging phase).
