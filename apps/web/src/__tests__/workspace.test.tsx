import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResearchWorkspace } from "@/components/layout/research-workspace";

vi.mock("@/components/graph/citation-canvas", () => ({
  CitationCanvas: () => <div aria-label="Citation graph">Graph canvas</div>,
}));
vi.mock("@/lib/api", async (importOriginal) => {
  const original = await importOriginal<typeof import("@/lib/api")>();
  return {
    ...original,
    api: {
      health: vi.fn().mockResolvedValue({ status: "ok" }),
      search: vi.fn().mockResolvedValue({
        papers: [
          {
            id: "W1",
            doi: null,
            title: "Fixture paper",
            year: 2024,
            authors: [],
            abstract: null,
            cited_by_count: 0,
            landing_page_url: null,
          },
        ],
        total: 1,
        page: 1,
        per_page: 10,
      }),
      neighbors: vi.fn().mockResolvedValue({ papers: [], citations: [] }),
    },
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

  it("returns to the starting prompt when TRACE is clicked", async () => {
    render(<ResearchWorkspace />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "Fixture" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Explore" }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Fixture paper/ }),
    );
    expect(screen.getByRole("button", { name: "Details" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "TRACE home" }));
    expect(
      screen.getByRole("heading", { name: "Follow the connections." }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Details" })).toBeNull();
  });
});
