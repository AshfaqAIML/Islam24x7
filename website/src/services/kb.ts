/**
 * Knowledge Base connection settings.
 *
 * The app never talks to the Knowledge Base directly from the browser —
 * only this services layer (imported by API routes / server components)
 * does. When KNOWLEDGE_BASE_API_URL is present the layer proxies the real
 * backend; otherwise it serves clearly-labeled demo data so every screen
 * can be designed honestly before the pipeline is ready.
 */
export type KbDataSource = "live" | "demo";

const KB_TIMEOUT_MS = 8_000;

export function kbDataSource(): KbDataSource {
  return process.env.KNOWLEDGE_BASE_API_URL ? "live" : "demo";
}

export function kbApiUrl(): string | null {
  const url = process.env.KNOWLEDGE_BASE_API_URL;
  if (!url) return null;
  return url.replace(/\/+$/, "");
}

/** fetch with timeout — never let a hanging KB backend freeze a route. */
export async function kbFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const base = kbApiUrl();
  if (!base) throw new Error("Knowledge Base API URL is not configured");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), KB_TIMEOUT_MS);
  try {
    const res = await fetch(`${base}${path}`, {
      ...init,
      signal: controller.signal,
      headers: { accept: "application/json", ...(init?.headers ?? {}) },
      cache: "no-store",
    });
    if (!res.ok) {
      throw new Error(`Knowledge Base responded ${res.status} for ${path}`);
    }
    return (await res.json()) as T;
  } finally {
    clearTimeout(timer);
  }
}
