/**
 * Device/platform detection — pure functions, safe on server and client.
 * Used by the first-visit APK prompt and the /download page to render
 * device-specific UI (never show Android install steps to iOS users).
 */
export type Platform = "android" | "ios" | "desktop";

export function getUaString(): string {
  if (typeof navigator === "undefined") return "";
  return navigator.userAgent ?? "";
}

export function isAndroid(ua: string = getUaString()): boolean {
  // Android phones/tablets (WebView included). Kindle Fire also reports Android.
  return /android/i.test(ua);
}

export function isIOS(ua: string = getUaString()): boolean {
  // iPadOS 13+ masquerades as Mac — include touch-capable Macs.
  if (/iphone|ipad|ipod/i.test(ua)) return true;
  return (
    /Macintosh/i.test(ua) &&
    typeof navigator !== "undefined" &&
    navigator.maxTouchPoints > 1
  );
}

export function detectPlatform(ua: string = getUaString()): Platform {
  if (isAndroid(ua)) return "android";
  if (isIOS(ua)) return "ios";
  return "desktop";
}

export function isMobilePlatform(p: Platform): boolean {
  return p === "android" || p === "ios";
}
