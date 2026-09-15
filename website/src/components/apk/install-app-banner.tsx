"use client";

import { useState } from "react";
import { Download, X } from "lucide-react";
import type { ApkReleaseStatus } from "@/types/knowledge-base";
import { brand } from "@/config/brand";
import { detectPlatform } from "@/lib/device";
import { useBrowserValue } from "@/hooks/use-client-store";
import { readJson, writeJson } from "@/lib/storage";
import { apkPromptStore } from "@/lib/apk-prompt-store";
import { Button } from "@/components/ui/button";
import { StarLattice } from "@/components/decor/islamic-pattern";

const BANNER_KEY = "ik.apkBanner.v1";
const PROMPT_KEY = "ik.apkPrompt.v1";

/**
 * Inline install banner for Android visitors (home page). Independent of the
 * first-visit modal: persists its own dismissal and hides once a download
 * has been recorded.
 */
export function InstallAppBanner({
  status,
  onDownload,
}: {
  status: ApkReleaseStatus | null;
  /** Optional override; by default the download is tracked (no PII). */
  onDownload?: (url: string) => void;
}) {
  const [locallyDismissed, setLocallyDismissed] = useState(false);

  const handleDownload = (url: string) => {
    if (onDownload) {
      onDownload(url);
      return;
    }
    void fetch("/api/downloads/track", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ platform: "android", source: "banner" }),
    }).catch(() => {});
    apkPromptStore.markDownloaded();
  };

  // Hydration-safe browser reads (SSR renders hidden; client updates after).
  const platform = useBrowserValue(detectPlatform, "desktop" as const);
  const override = useBrowserValue(
    () => new URLSearchParams(window.location.search).get("apkPrompt"),
    null
  );
  const downloaded = useBrowserValue(
    () =>
      readJson<{ downloadedAt?: number } | null>(PROMPT_KEY, null)
        ?.downloadedAt != null,
    false
  );
  const storedDismissed = useBrowserValue(
    () => readJson<boolean>(BANNER_KEY, false),
    true
  );

  const androidLike =
    platform === "android" || override === "auto" || override === "1";
  const visible =
    androidLike && !storedDismissed && !locallyDismissed && !downloaded;

  if (!visible) return null;

  const release = status?.release;
  const available = status?.available ?? false;

  return (
    <aside
      aria-label="Get the Android app"
      className="relative overflow-hidden rounded-xl border border-gold/30 bg-gradient-to-r from-primary/10 via-primary/5 to-gold/10"
    >
      <StarLattice
        tile={44}
        className="absolute inset-0 h-full w-full text-gold opacity-[0.08]"
      />
      <div className="relative flex items-center gap-3 p-4">
        <img
          src={brand.appIcon}
          alt=""
          width={44}
          height={44}
          className="rounded-xl shadow ring-1 ring-black/5"
          aria-hidden="true"
        />
        <div className="min-w-0 flex-1">
          <p className="text-sm font-semibold">{brand.name} for Android</p>
          <p className="truncate text-xs text-muted-foreground">
            {available
              ? `Version ${release?.version ?? "—"}${
                  release?.sizeLabel ? ` · ${release.sizeLabel}` : ""
                } · Free download`
              : "Release pending — the web app works fully in your browser."}
          </p>
        </div>
        {available && release ? (
          <Button asChild size="sm" onClick={() => handleDownload(release.downloadUrl)}>
            <a href={release.downloadUrl} download>
              <Download className="h-4 w-4" aria-hidden="true" />
              Get APK
            </a>
          </Button>
        ) : (
          <Button size="sm" variant="outline" disabled>
            Unavailable
          </Button>
        )}
        <button
          type="button"
          aria-label="Dismiss install banner"
          onClick={() => {
            setLocallyDismissed(true);
            writeJson(BANNER_KEY, true);
            apkPromptStore.dismiss();
          }}
          className="focus-ring rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-background/70 hover:text-foreground"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
    </aside>
  );
}
