import type { MetadataRoute } from "next";
import { siteConfig, routes } from "@/config/site";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${siteConfig.url}${routes.home}`, lastModified: now, changeFrequency: "weekly", priority: 1 },
    { url: `${siteConfig.url}${routes.library}`, lastModified: now, changeFrequency: "daily", priority: 0.9 },
    { url: `${siteConfig.url}${routes.search}`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
    { url: `${siteConfig.url}${routes.download}`, lastModified: now, changeFrequency: "weekly", priority: 0.8 },
  ];
}
