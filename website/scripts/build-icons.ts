/**
 * Brand asset pipeline (Phase 1)
 * Derives web/PWA icon sizes from public/icons/icon-master.png
 * and an Open Graph image from public/icons/og-master.png.
 *
 * Run: bun run scripts/build-icons.ts
 */
import sharp from "sharp";
import fs from "fs";
import path from "path";

const ICONS_DIR = path.join(process.cwd(), "public", "icons");
const MASTER_ICON = path.join(ICONS_DIR, "icon-master.png");
const MASTER_OG = path.join(ICONS_DIR, "og-master.png");

async function main() {
  if (!fs.existsSync(MASTER_ICON)) {
    console.error("Missing icon-master.png — generate it first.");
    process.exit(1);
  }

  const sizes: Array<[number, string]> = [
    [512, "icon-512.png"],
    [192, "icon-192.png"],
    [180, "apple-touch-icon.png"],
  ];

  for (const [size, name] of sizes) {
    await sharp(MASTER_ICON)
      .resize(size, size, { fit: "cover" })
      .png({ compressionLevel: 9 })
      .toFile(path.join(ICONS_DIR, name));
    console.log(`✓ ${name} (${size}x${size})`);
  }

  // Favicon (32px PNG — modern browsers)
  await sharp(MASTER_ICON)
    .resize(32, 32, { fit: "cover" })
    .png()
    .toFile(path.join(ICONS_DIR, "favicon-32.png"));
  console.log("✓ favicon-32.png");

  if (fs.existsSync(MASTER_OG)) {
    // Standard OG ratio 1200x630 (center-crop from 1344x768)
    await sharp(MASTER_OG)
      .resize(1200, 630, { fit: "cover", position: "centre" })
      .jpeg({ quality: 82 })
      .toFile(path.join(ICONS_DIR, "og-image.jpg"));
    console.log("✓ og-image.jpg (1200x630)");
  }

  console.log("Icon pipeline complete.");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
