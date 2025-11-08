import type { MetadataRoute } from 'next';

export default function sitemap(): MetadataRoute.Sitemap {
  const base = 'https://gaafixturesresults.vercel.app';
  return [
    { url: `${base}/`, changeFrequency: 'hourly', priority: 0.8 },
    { url: `${base}/fixtures`, changeFrequency: 'hourly', priority: 1.0 },
    { url: `${base}/results`, changeFrequency: 'hourly', priority: 0.9 },
  ];
}

