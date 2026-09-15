import type { Metadata, Viewport } from "next";
import { Inter, Lora, Amiri } from "next/font/google";
import { ThemeProvider } from "next-themes";
import "./globals.css";
import { Toaster } from "@/components/ui/toaster";
import { brand } from "@/config/brand";
import { siteConfig } from "@/config/site";
import { SiteHeader } from "@/components/layout/site-header";
import { SiteFooter } from "@/components/layout/site-footer";
import { BottomTabBar } from "@/components/layout/bottom-tab-bar";
import { ApkPromptProvider } from "@/components/apk/apk-prompt-provider";

const bodyFont = Inter({
  subsets: ["latin"],
  variable: "--font-body",
  display: "swap",
});

const displayFont = Lora({
  subsets: ["latin"],
  variable: "--font-display",
  style: ["normal", "italic"],
  display: "swap",
});

/** Arabic text face for Quran/Hadith/Duas (used from Phase 6 onwards). */
const arabicFont = Amiri({
  subsets: ["arabic"],
  weight: ["400", "700"],
  variable: "--font-arabic-text",
  display: "swap",
});

export const metadata: Metadata = {
  metadataBase: new URL(siteConfig.url),
  title: {
    default: `${brand.name} — Quran, Hadith, Library & AI Research`,
    template: `%s · ${brand.name}`,
  },
  description: brand.description,
  keywords: [
    "Islam",
    "Quran",
    "Hadith",
    "Islamic library",
    "Fiqh",
    "Tafsir",
    "Islamic knowledge",
  ],
  applicationName: brand.name,
  manifest: "/manifest.webmanifest",
  icons: {
    icon: [{ url: "/icons/favicon-32.png", sizes: "32x32", type: "image/png" }],
    apple: [{ url: "/icons/apple-touch-icon.png", sizes: "180x180" }],
  },
  openGraph: {
    type: "website",
    siteName: brand.name,
    title: `${brand.name} — ${brand.tagline}`,
    description: brand.description,
    images: [{ url: brand.ogImage, width: 1200, height: 630, alt: brand.name }],
  },
  twitter: {
    card: "summary_large_image",
    title: `${brand.name} — ${brand.tagline}`,
    description: brand.description,
    images: [brand.ogImage],
  },
  robots: { index: true, follow: true },
};

export const viewport: Viewport = {
  width: "device-width",
  initialScale: 1,
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: brand.themeColorLight },
    { media: "(prefers-color-scheme: dark)", color: brand.themeColorDark },
  ],
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${bodyFont.variable} ${displayFont.variable} ${arabicFont.variable} flex min-h-svh flex-col bg-background font-sans text-foreground antialiased`}
      >
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <a
            href="#main-content"
            className="focus-ring sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-primary-foreground"
          >
            Skip to main content
          </a>
          <SiteHeader />
          <div id="main-content" className="flex flex-1 flex-col">
            {children}
          </div>
          <SiteFooter />
          {/* Clearance for the fixed mobile tab bar so it never covers the footer */}
          <div
            aria-hidden="true"
            className="h-[calc(4.5rem+env(safe-area-inset-bottom))] md:hidden"
          />
          <BottomTabBar />
          <ApkPromptProvider />
          <Toaster />
        </ThemeProvider>
      </body>
    </html>
  );
}
