import { createFileRoute } from "@tanstack/react-router";
import { ArchApp } from "@/components/arch/ArchApp";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Arch Morning View — Capital calls due today" },
      { name: "description", content: "Review unpaid capital calls and investor letters for each client, soonest due first." },
      { property: "og:title", content: "Arch Morning View" },
      { property: "og:description", content: "Review unpaid capital calls and investor letters for each client." },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary" },
    ],
  }),
  component: ArchApp,
});
