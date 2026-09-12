import type { MetadataRoute } from "next";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: "Avenqo — AI Business Operating System",
    short_name: "Avenqo",
    description:
      "Plateforme SaaS B2B modulaire pour les entreprises : Retail Intelligence, intégrations et décisions stratégiques unifiées.",
    start_url: "/",
    display: "standalone",
    background_color: "#07090e",
    theme_color: "#07090e",
    icons: [
      {
        src: "/brand/avenqo-icon.png",
        sizes: "192x192",
        type: "image/png",
      },
      {
        src: "/brand/avenqo-icon.png",
        sizes: "512x512",
        type: "image/png",
      },
    ],
  };
}
