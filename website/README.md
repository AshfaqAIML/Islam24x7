# Islam24x7

> **Read. Search. Learn. Explore.**

Islam24x7 is a modern Islamic knowledge platform for reading the Quran,
exploring Hadith, browsing a structured Islamic library, and asking an AI
research assistant — every answer grounded in verifiable, citable sources.
One codebase ships both a **responsive web app** and an **installable Android
APK**.

---

## Overview

Islam24x7 puts the reader first: **search → find sources → read the original
passage → resume anywhere.** It is deliberately built as the *interface* to a
dedicated Islamic Knowledge Base — not a source of truth itself. Content flows
one way, from an approved ingestion pipeline through clean REST APIs to your
screen, so nothing is ever faked or fabricated.

| | |
|---|---|
| **What** | Quran, Hadith, Islamic library, and a source-grounded AI research assistant |
| **Platforms** | Web (Responsive + PWA-ready) and Android (Capacitor) from one codebase |
| **Stack** | Next.js 16 · React 19 · TypeScript · Tailwind CSS 4 · shadcn/ui · Prisma |
| **Status** | Phases 1–5 shipped (Foundation, Home, Library, Reader, Global Search) |

---

## Key features

### Library & Reading
- **Structured library** — browse Fiqh, Tafsir, Aqeedah, Seerah and history
  volumes with detail views and favorites (`/library`, `/library/[bookId]`).
- **Reader** — a focused e-book reading experience with per-book reading
  progress, resume support, configurable typography and themes, and
  deep-linkable URLs that open any book (`/library/[bookId]/read`).
- **Home dashboard** — greeting, daily ayah, tasbeeh counter, continue-reading
  shortcut and quick access to search.

### Search
- **Global search** across All, Quran, Hadith, Books and Dua scopes
  (`/search`), with rich result cards, breadcrumbs and highlighted excerpts.
- Not-yet-built scopes return an honest empty state — never fabricated hits.

### AI Assistant
- **Ask-the-library foundation** is live (`/ai`): scope a question to the
  whole library, a book or a chapter. Every answer will carry clickable
  citations (Book → Chapter → Page, Surah → Ayah, Collection → Number) and the
  AI summary is visually distinct from the source text.

### Android & APK delivery
- **Config-driven release system** — version, changelog, size and minimum
  Android version come from environment variables; nothing hard-coded.
- **Live availability check** — `GET /api/releases/latest` probes the artifact
  (filesystem or remote URL) so the UI always shows the truth and degrades
  gracefully when a release is unavailable.
- **First-visit prompt** — Android visitors are invited to install once, with
  persistent dismissal and a re-trigger window. QA overrides:
  `?apkPrompt=1|auto|0`.
- **Install page** — dedicated `/download` with step-by-step instructions,
  security notes, download tracking and honest unavailability messaging.

### Design system & polish
- **Original brand identity** — deep emerald and warm gold, an eight-pointed
  star mark, subtle Islamic geometric lattice decoration, light/dark/system
  themes.
- **Mobile-first responsive shell** — accessible header, sticky footer,
  bottom tab bar, touch-friendly targets, reduced-motion and keyboard focus
  support.
- **Reusable UI kit** — `BookCard`, `SourceCitation`, Empty/Error/Loading
  states, `DemoBadge` and more, all typed and config-driven.
- **SEO & PWA seeding** — metadata, Open Graph, web manifest, robots and
  sitemap.

---

## Content integrity (non-negotiable)

1. **No Quran verse, hadith, ruling or quotation is ever generated or faked.**
2. Mock/demo content lives only in `src/lib/demo/*`, is flagged `isDemo`, and
   is always rendered with a visible **Demo** badge.
3. AI answers always carry clickable citations; generated summaries and source
   excerpts are visually distinct.
4. When a backend is unavailable, the UI shows an honest unavailable state —
   never empty or invented content.

---

## Architecture

```
Islamic Knowledge Base (Python ingestion pipeline — external)
        │  REST / search / RAG endpoints
        ▼
Next.js backend (API routes — the only place secrets live)
        │  typed client (src/services — mock & remote providers)
        ▼
Web (App Router, mobile-first PWA)  ⇄  Android APK (Capacitor wrapper)
```

- The service layer (`src/services/*`) is the **only** consumer of the
  Knowledge Base — swap mock and remote providers without touching the UI.
- The typed API contract lives in `src/types/knowledge-base.ts`, the single
  source of truth for all data shapes.
- Config is centralized (`src/config/*`): brand, site, feature flags and
  APK release metadata — **zero content hard-coded in components**.
- Secrets live server-side only (`DATABASE_URL`, `KNOWLEDGE_BASE_API_URL`,
  `AI_API_URL`); nothing sensitive ever reaches the client.

---

## Tech stack

| Layer | Technology |
|---|---|
| Framework | Next.js 16 (App Router) |
| UI | React 19, Tailwind CSS 4, shadcn/ui, Radix, Framer Motion, Lucide |
| Data | Prisma (SQLite), TanStack Query, Zustand stores |
| Forms/Validation | React Hook Form, Zod |
| Mobile | Capacitor (Android) |
| Quality | TypeScript, ESLint, tests in `tests/` |

---

## Getting started

### Prerequisites

- **Bun** (or Node.js 20+)

### Setup

```bash
bun install
bun run dev              # start the dev server → http://localhost:3000
```

Set up `.env` from the variables documented in [`docs/SETUP.md`](docs/SETUP.md)
— including `NEXT_PUBLIC_USE_MOCK_DATA=true` to run in clearly-labeled demo
mode while the Knowledge Base backend is being connected.

### Common commands

| Command | Purpose |
|---|---|
| `bun run dev` | Dev server on `:3000` (logs → `dev.log`) |
| `bun run build` | Production build (Next.js standalone) |
| `bun run start` | Serve the standalone production build |
| `bun run lint` | ESLint / Next.js rules |
| `bun run db:push` | Push the Prisma schema (personal-data phases) |
| `bun run scripts/build-icons.ts` | Regenerate brand assets from masters |

### Testing the first-visit APK flow

- Any desktop browser sees no prompt (by design).
- `?apkPrompt=auto` — simulate an Android visitor, respecting dismissal state.
- `?apkPrompt=1` — force-show, ignoring dismissal.
- `?apkPrompt=0` — force-hide.

---

## Roadmap

| Phase | Module |
|---|---|
| 1–2 | Foundation, Home/Nav shell ✅ |
| 3 | Library ✅ |
| 4 | Reader ✅ |
| 5 | Global search ✅ |
| 6 | Quran (surah / ayah views) |
| 7 | Hadith browser |
| 8 | Bookmarks, notes & synced progress |
| 9 | AI Assistant (ask library / book / chapter, research mode) |
| 10 | Duas & Azkar (counters, routines) |
| 11 | Prayer times, Qibla, Tasbeeh |
| 12 | PWA service worker, offline shell |
| 13 | Capacitor Android build & release management |
| 14–16 | Polish, testing, accessibility, performance, production deployment |

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the full screen map.

---

## Documentation

- [`docs/SETUP.md`](docs/SETUP.md) — environment and configuration
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — system design & screen map
- [`docs/API.md`](docs/API.md) — API contract
- [`docs/APK_RELEASE.md`](docs/APK_RELEASE.md) — APK release workflow
- [`docs/ANDROID.md`](docs/ANDROID.md) — Android build guide