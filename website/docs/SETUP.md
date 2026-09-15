# Setup — Islam24x7

## Prerequisites

- Bun (or Node 20+)
- The external Islamic Knowledge Base (optional in early phases — mock mode)

## Environment

Copy `.env.example` → `.env`. Key variables:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | SQLite (Prisma) for personal data (Phase 8+) |
| `KNOWLEDGE_BASE_API_URL` | Base URL of the external Knowledge Base API |
| `AI_API_URL` | AI/RAG endpoint (Phase 9). Keys stay server-side |
| `NEXT_PUBLIC_USE_MOCK_DATA` | `true` → clearly-labeled demo data mode |
| `APK_DOWNLOAD_URL` | `/downloads/…` or any https URL (CDN/GitHub) |
| `APK_VERSION` / `APK_RELEASE_DATE` / `APK_SIZE_LABEL` / `APK_MIN_ANDROID_VERSION` / `APK_CHANGELOG` | Release metadata surfaced on `/download` & the first-visit prompt |
| `NEXT_PUBLIC_APK_PROMPT_ENABLED` | Master switch for the first-visit APK prompt |
| `NEXT_PUBLIC_APK_PROMPT_RETRIGGER_DAYS` | Days to stay quiet after dismissal |
| `NEXT_PUBLIC_SITE_URL` | Canonical URL for SEO metadata |

Never put secrets in `NEXT_PUBLIC_*` variables.

## Commands

```bash
bun install
bun run dev        # dev server on :3000 (logs → dev.log)
bun run lint       # ESLint / Next.js rules
bun run db:push    # push Prisma schema (personal-data phases)
bun run scripts/build-icons.ts   # derive icons from public/icons/*master.png
```

## Testing the first-visit APK flow

- Any desktop browser: no prompt (by design).
- `?apkPrompt=auto` — simulate an Android visitor while respecting
  dismissal state (full flow: show → dismiss → reload → hidden).
- `?apkPrompt=1` — force show, ignoring dismissal.
- `?apkPrompt=0` — force hide.
- `GET /api/downloads/track` shows the in-memory download counters.
- The `/download` page reports “unavailable” honestly until an APK artifact
  is placed in `public/downloads/islamic-knowledge.apk` (or
  `APK_DOWNLOAD_URL` points at a reachable host).
