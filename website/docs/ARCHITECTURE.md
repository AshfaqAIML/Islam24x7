# Architecture — Islam24x7

> Status: **Phases 1–5 shipped** (foundation, home/nav shell, library, reader,
> global search) plus the Phase-1 acceptance alignment round: product renamed
> to **Islam24x7** (config-driven, `src/config/brand.ts`), AI foundation page
> live (honest not-connected state), citation deep-linking (`openCitation`).
> This document is the authoritative architecture proposal for the whole product.

## 1. Product principle

The application is **not** the Knowledge Base. It is the interface to it.

```
Islamic Knowledge Base (Python ingestion pipeline — external)
        ↓  REST / search / RAG endpoints
Next.js 16 backend (API routes — the only place secrets live)
        ↓  typed client (src/services — mock & remote providers)
Web (App Router, mobile-first PWA)  ⇄  Android APK (Capacitor wrapper)
```

Core loop: **Search / Browse / Ask AI → find sources → read the original
passage → bookmark / highlight / note → continue research.**

## 2. Repository layout (Next.js App Router adaptation)

```
src/
├── app/                      # routes (/, /download, /api/*)
│   ├── api/                  # knowledge-base proxy + personal data + releases
│   ├── download/             # APK install page
│   ├── manifest.ts robots.ts sitemap.ts
├── components/
│   ├── ui/                   # shadcn/ui primitives (pre-installed)
│   ├── brand/                # logo, brand mark
│   ├── decor/                # Islamic geometric patterns (aria-hidden)
│   ├── common/               # EmptyState, ErrorState, LoadingState, badges
│   ├── layout/               # header, footer, theme toggle
│   ├── apk/                  # first-visit prompt, banner, download page bits
│   ├── home/ books/ citations/
│   └── <feature>/            # added per phase (quran, hadith, reader, ai…)
├── config/                   # brand.ts, site.ts, apk-release.ts (env-driven)
├── hooks/                    # use-apk-prompt, (reader/settings hooks later)
├── lib/                      # device, storage, db, utils, demo/
├── services/                 # THE ONLY KB consumer (mock + remote providers)
└── types/knowledge-base.ts   # API contract types (single source of truth)
public/
├── icons/                    # generated brand assets (icon pipeline script)
└── downloads/                # APK release artifact location
docs/  scripts/  android/     # docs, asset scripts, Capacitor shell (Phase 13)
```

## 3. API contract assumptions

Types live in `src/types/knowledge-base.ts`. Planned endpoints (adapt, don't
invent — the service layer is the only place that changes):

```
GET  /api/books?category=&q=&page=          → Paginated<Book>
GET  /api/books/:id                         → Book
GET  /api/books/:id/chapters                → BookChapter[]
GET  /api/books/:id/pages?chapterId=&page=  → Paginated<BookPage>
GET  /api/search?q=&scope=all|quran|hadith|books|dua
GET  /api/quran/surahs                      → Surah[]
GET  /api/quran/surahs/:id?translation=     → Surah & Ayah[]
GET  /api/hadith/collections                → HadithCollection[]
GET  /api/hadith?collection=&page=          → Paginated<Hadith>
POST /api/ai/ask { question, scope, bookId? } → { answer, citations: Citation[] }
GET/POST /api/bookmarks | /api/notes | /api/reading-progress
```

Environment: `KNOWLEDGE_BASE_API_URL`, `AI_API_URL`, `APK_DOWNLOAD_URL`,
`NEXT_PUBLIC_USE_MOCK_DATA` (see `.env.example`). **No secret ever reaches the
client** — client components call our own `/api/*` routes.

## 4. Web / Android strategy

- **One codebase.** Next.js 16 + React 19 + Tailwind 4 + shadcn/ui.
- **Android = Capacitor** wrapping the production web build (Phase 13):
  native splash, app icon, hardware back handling, deep links
  (`ik://book/:id/ch/:ch/page/:p`), share target, network-state UX.
- Scripts (added Phase 13): `build:web`, `build:android`,
  `build:android:release` (keystore via env vars, never committed).
- PWA (Phase 12) is the *web install* path; the APK is the *native artifact*.
  They are separate delivery channels and must not be conflated.

## 5. APK release strategy

- Artifact: `public/downloads/islamic-knowledge.apk` or any URL via
  `APK_DOWNLOAD_URL` (CDN / GitHub Releases / cloud storage).
- Release metadata: `APK_VERSION`, `APK_RELEASE_DATE`, `APK_SIZE_LABEL`,
  `APK_MIN_ANDROID_VERSION`, `APK_CHANGELOG` (env-driven, zero hard-coding).
- Public endpoint `GET /api/releases/latest` performs a live availability
  check (fs for local paths, HEAD for remote) → UI always shows the truth and
  degrades gracefully (“currently unavailable → continue on web”).
- First-visit flow: Android detection → first visit (`localStorage`) →
  elegant prompt → Download / Continue on web / Dismiss. Dismissal persists
  for `NEXT_PUBLIC_APK_PROMPT_RETRIGGER_DAYS` days; download permanently
  silences auto-prompts. QA overrides: `?apkPrompt=1|auto|0`.
- Download analytics: `POST /api/downloads/track` (no PII; durable storage in
  Phase 13).

## 6. UI screen map

| Route | Module | Phase |
|---|---|---|
| `/` | Home dashboard (prayer, continue reading, daily verse/hadith) | 1–2 |
| `/download` | APK install page (live availability, steps, security notice) | 1 |
| `/library`, `/library/[bookId]` | Library, book detail | 3 |
| `/library/[bookId]/read` | Reader (TOC, themes, highlights, deep-linkable) | 4 |
| `/search` | Global search (All/Quran/Hadith/Books/Dua) | 5 |
| `/quran` (+ surah/ayah views) | Quran | 6 |
| `/hadith` | Hadith browser | 7 |
| bookmarks/notes/progress | Personal layer (auth-optional sync) | 8 |
| `/ai` | AI assistant (Ask Library/Book/Chapter, Research mode) | 9 |
| `/duas`, `/azkar` | Duas & Azkar (counters, routines) | 10 |
| `/prayer`, `/qibla`, `/tasbeeh` | Prayer times, Qibla, Tasbeeh | 11 |
| PWA service worker, offline shell | — | 12 |
| Capacitor Android build + release mgmt | — | 13 |
| First-visit APK flow polish | (foundation already live) | 14 |
| Tests, a11y, performance | — | 15 |
| Production build & deploy | — | 16 |

## 7. Design system

- **Identity**: deep emerald `--primary` (oklch ~0.44/0.088/165) + warm gold
  `--gold` on warm paper; dark mode is deep green-ink. Original brand mark:
  eight-pointed star (two overlapping squares) — `components/brand/logo.tsx`.
- **Type**: Inter (UI), Lora (display/serif), Amiri (Arabic, Phase 6+).
- **Pattern**: `StarLattice` — classical eight-point-star tile, `currentColor`,
  low opacity, always `aria-hidden`.
- **States**: EmptyState / ErrorState / LoadingState are mandatory for every
  async surface. Demo data is always flagged with `DemoBadge`.
- **A11y**: semantic landmarks, skip link, 44px touch targets, reduced-motion
  support, keyboard focus rings (`.focus-ring`), safe-area-aware footer.
- **Footer**: sticky bottom via `min-h-svh flex flex-col` + `mt-auto`.

## 8. Content integrity rules (non-negotiable)

1. No Quran verse, hadith, ruling or quotation is ever generated or faked.
2. Mock data exists only in `src/lib/demo/*`, flagged `isDemo`, rendered with
   a visible “Demo” badge.
3. AI answers always carry clickable citations (Book → Chapter → Page /
   Surah → Ayah / Collection → Number); AI summary and source text are
   visually distinct.
4. When a backend is missing, the UI shows an honest *unavailable* state —
   never empty fake content.
