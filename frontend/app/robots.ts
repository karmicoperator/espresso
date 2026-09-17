import type { MetadataRoute } from "next";

/** Nothing here is meant to be indexed. If this ever gets a public host, it stays out. */
export default function robots(): MetadataRoute.Robots {
  return {
    rules: { userAgent: "*", disallow: "/" },
  };
}
