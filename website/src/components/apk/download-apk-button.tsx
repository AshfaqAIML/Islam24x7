"use client";

import { Download } from "lucide-react";
import type { ApkRelease } from "@/types/knowledge-base";
import { useApkPrompt } from "@/hooks/use-apk-prompt";
import { Button } from "@/components/ui/button";
import { useToast } from "@/hooks/use-toast";

/**
 * The real APK download action. Records the download (prompt state +
 * analytics beacon) without ever blocking or intercepting the file itself.
 */
export function DownloadApkButton({
  release,
  size = "lg",
  className,
}: {
  release: ApkRelease;
  size?: "sm" | "default" | "lg";
  className?: string;
}) {
  const { markDownloaded } = useApkPrompt();
  const { toast } = useToast();

  return (
    <Button
      asChild
      size={size}
      className={className}
      onClick={() => {
        markDownloaded();
        try {
          void fetch("/api/downloads/track", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              version: release.version,
              surface: "download-page",
            }),
            keepalive: true,
          });
        } catch {
          // analytics must never block the download
        }
        toast({
          title: "Download started",
          description:
            "If nothing happens, check that your browser allows downloads from this site.",
        });
      }}
    >
      <a href={release.downloadUrl} download>
        <Download className="h-5 w-5" aria-hidden="true" />
        Download APK ({release.sizeLabel || `v${release.version}`})
      </a>
    </Button>
  );
}
