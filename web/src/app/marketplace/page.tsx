import { AppShell } from "@/components/shell/app-shell";
import { MarketplaceView } from "@/components/workspace/marketplace-view";

export const metadata = { title: "Marketplace | Avenqo", robots: { index: false, follow: false } };

export default function MarketplacePage() {
  return <AppShell><MarketplaceView /></AppShell>;
}
