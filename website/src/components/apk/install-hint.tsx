"use client";

import { Smartphone, MonitorSmartphone, Apple } from "lucide-react";
import { detectPlatform, type Platform } from "@/lib/device";
import { useBrowserValue } from "@/hooks/use-client-store";

/**
 * Device-specific install guidance — Android users get direct steps,
 * iOS users are told clearly that there is no iOS APK (no misleading
 * instructions), desktop gets a neutral note. SSR renders the neutral note
 * and the client refines it after hydration.
 */
export function InstallHint() {
  const platform: Platform = useBrowserValue(detectPlatform, "desktop");

  if (platform === "android") {
    return (
      <p className="flex items-start gap-2 rounded-lg bg-secondary/60 p-3 text-sm text-secondary-foreground">
        <Smartphone className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          You&apos;re browsing on Android — the download button above installs
          directly on this device.
        </span>
      </p>
    );
  }

  if (platform === "ios") {
    return (
      <p className="flex items-start gap-2 rounded-lg bg-muted p-3 text-sm text-muted-foreground">
        <Apple className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
        <span>
          This is the Android installer. There is no iOS app yet — on iPhone or
          iPad, use the web app and add it to your home screen from the share
          menu.
        </span>
      </p>
    );
  }

  return (
    <p className="flex items-start gap-2 rounded-lg bg-muted p-3 text-sm text-muted-foreground">
      <MonitorSmartphone className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      <span>
        You&apos;re on a desktop browser. Open this page on your Android device
        to install the app — or simply keep using the full web experience.
      </span>
    </p>
  );
}
