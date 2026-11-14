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
  it("centers the starting prompt before a graph is selected", async () => {
    render(<ResearchWorkspace />);
    expect(
      screen.getByRole("searchbox", {
        name: "Search scientific papers or paste an article link",
      }),
    ).toBeDefined();
    expect(
      screen.getByRole("heading", { name: "Follow the connections." }),
    ).toBeInTheDocument();
    expect(screen.queryByText("A closer look")).toBeNull();
  });
});
