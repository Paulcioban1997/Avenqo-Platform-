import { fireEvent, render, screen } from "@testing-library/react";
import { expect, it, vi } from "vitest";
import { GlobalSourceSelector } from "@/components/shell/global-source-selector";

const { reload } = vi.hoisted(() => ({ reload: vi.fn(async () => {}) }));
vi.mock("@/lib/i18n/locale-context", () => ({ useLocale: () => ({ locale: "en" }) }));
vi.mock("@/lib/session-context", () => ({
  useSession: () => ({
    sourceContext: null,
    sourceChoices: [],
    sourceSelectionState: "unconfirmed",
    sourceError: new Error("Context unavailable"),
    reload,
  }),
}));

it("allows a context reload when there are no retained source choices", () => {
  render(<GlobalSourceSelector />);
  fireEvent.click(screen.getByRole("button", { expanded: false }));
  fireEvent.click(screen.getByRole("menuitem", { name: /retry/i }));
  expect(reload).toHaveBeenCalledOnce();
});
