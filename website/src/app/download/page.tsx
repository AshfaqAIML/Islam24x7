import type { Metadata } from "next";
import Link from "next/link";
import Image from "next/image";
import { CircleAlert, ShieldCheck } from "lucide-react";
import { getApkRelease, isApkAvailable } from "@/config/apk-release";
import { brand } from "@/config/brand";
import { routes } from "@/config/site";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { ErrorState } from "@/components/common/states";
import { DownloadApkButton } from "@/components/apk/download-apk-button";
import { InstallHint } from "@/components/apk/install-hint";
import { StarLattice } from "@/components/decor/islamic-pattern";

export const metadata: Metadata = {
  title: "Get the Android App",
  description: `Download the ${brand.name} Android app (APK): read, search and study the Islamic library on the go.`,
  alternates: { canonical: routes.download },
};

export const dynamic = "force-dynamic";

const installSteps = [
  "Tap Download APK and wait for the file to finish.",
  "Open the downloaded file from your notifications or Downloads folder.",
  "If Android asks, allow installs from this source (your browser).",
  "Tap Install, then open the app and start exploring.",
];

export default async function DownloadPage() {
  const release = getApkRelease();
  const { available, reason } = await isApkAvailable();

  return (
    <div className="relative">
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-primary/10 to-transparent"
      />
      <StarLattice
        tile={64}
        className="absolute inset-x-0 top-0 h-40 w-full text-gold opacity-[0.07]"
      />

      <main className="relative mx-auto max-w-2xl px-4 py-12 sm:py-16">
        <div className="text-center">
          <Image
            src={brand.appIcon}
            alt={`${brand.name} app icon`}
            width={96}
            height={96}
            priority
            className="mx-auto rounded-3xl shadow-lg ring-1 ring-black/5"
          />
          <h1 className="mt-4 font-serif text-3xl font-semibold tracking-tight sm:text-4xl">
            {brand.name}
          </h1>
          <p className="mt-1 text-sm text-muted-foreground">
            Android App · Version {release.version}
          </p>
        </div>

        {available ? (
          <Card className="mt-8">
            <CardContent className="p-6">
              <div className="flex flex-wrap items-center justify-center gap-2 text-xs text-muted-foreground">
                {release.sizeLabel ? (
                  <span className="rounded-full bg-muted px-2.5 py-1">
                    Size: {release.sizeLabel}
                  </span>
                ) : null}
                {release.releaseDate ? (
                  <span className="rounded-full bg-muted px-2.5 py-1">
                    Released: {release.releaseDate}
                  </span>
                ) : null}
                {release.minAndroidVersion ? (
                  <span className="rounded-full bg-muted px-2.5 py-1">
                    Requires Android {release.minAndroidVersion}+
                  </span>
                ) : null}
              </div>

              <div className="mt-6 flex justify-center">
                <DownloadApkButton release={release} />
              </div>

              {release.changelog && release.changelog.length > 0 ? (
                <div className="mt-6 rounded-lg border bg-card p-4">
                  <h2 className="text-sm font-semibold">What&apos;s new</h2>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                    {release.changelog.map((entry) => (
                      <li key={entry}>{entry}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="mt-6">
                <InstallHint />
              </div>

              <Separator className="my-6" />

              <section aria-labelledby="how-to-install">
                <h2
                  id="how-to-install"
                  className="font-serif text-lg font-semibold"
                >
                  How to install
                </h2>
                <ol className="mt-3 space-y-2.5">
                  {installSteps.map((step, i) => (
                    <li key={step} className="flex items-start gap-3 text-sm">
                      <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary text-xs font-semibold text-primary-foreground">
                        {i + 1}
                      </span>
                      <span className="pt-0.5 text-foreground/90">{step}</span>
                    </li>
                  ))}
                </ol>
              </section>

              <div
                role="note"
                className="mt-6 flex items-start gap-2.5 rounded-lg border border-gold/30 bg-gold/10 p-3.5"
              >
                <ShieldCheck
                  className="mt-0.5 h-4 w-4 shrink-0 text-gold-foreground dark:text-gold"
                  aria-hidden="true"
                />
                <p className="text-xs leading-relaxed text-gold-foreground dark:text-gold/90">
                  <strong>Security notice:</strong> only download this app from
                  this official page. Android may warn about apps installed
                  outside the Play Store — that is expected for direct APK
                  distribution. If you did not expect this file, cancel the
                  installation.
                </p>
              </div>
            </CardContent>
          </Card>
        ) : (
          <div className="mt-8">
            <ErrorState
              title="The Android app is currently unavailable"
              description={
                reason ??
                "The release artifact could not be reached. You can continue using the web application right now."
              }
              retryLabel="Check again"
            />
            <p className="mt-4 text-center text-sm text-muted-foreground">
              Version {release.version} is planned — this page will light up as
              soon as the release artifact is published.
            </p>
          </div>
        )}

        {/* Web alternative — never trap the visitor (#60) */}
        <Card className="mt-6">
          <CardContent className="flex flex-col items-center gap-3 p-6 text-center sm:flex-row sm:text-left">
            <div className="flex-1">
              <h2 className="font-serif text-base font-semibold">
                Prefer not to install?
              </h2>
              <p className="mt-1 text-sm text-muted-foreground">
                The full experience — library, reader, search — runs in your
                browser with nothing to install.
              </p>
            </div>
            <Button asChild variant="outline">
              <Link href={routes.home}>Continue on web</Link>
            </Button>
          </CardContent>
        </Card>

        <p className="mt-8 flex items-center justify-center gap-1.5 text-center text-xs text-muted-foreground">
          <CircleAlert className="h-3.5 w-3.5" aria-hidden="true" />
          Having trouble? Reload this page — availability is checked live.
        </p>
      </main>
    </div>
  );
}
