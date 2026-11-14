import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResearchWorkspace } from "@/components/layout/research-workspace";

vi.mock("@/components/graph/citation-canvas", () => ({
  CitationCanvas: () => <div aria-label="Citation graph">Graph canvas</div>,
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    api: { health: vi.fn().mockResolvedValue({ status: "ok" }) },
  };
});

describe("ResearchWorkspace", () => {
  it("renders search, empty details and a backend connection", async () => {
    render(<ResearchWorkspace />);
    expect(
      screen.getByRole("searchbox", { name: "Search scientific papers" }),
    ).toBeDefined();
    expect(screen.getByText("A closer look")).toBeInTheDocument();
    expect(await screen.findByText("API connected")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Saved graphs" })).toBeDisabled();
  });
});
