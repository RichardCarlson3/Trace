import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useImperativeHandle, type Ref } from "react";
import { ResearchWorkspace } from "@/components/layout/research-workspace";
import type { CitationCanvasHandle } from "@/components/graph/citation-canvas";
import { api } from "@/lib/api";
import { SAVED_GRAPHS_KEY } from "@/lib/browser-library";

vi.mock("@/components/graph/citation-canvas", () => ({
  CitationCanvas: ({ ref }: { ref?: Ref<CitationCanvasHandle> }) => {
    useImperativeHandle(ref, () => ({
      getLayout: () => ({
        positions: { W1: { x: 150, y: -20 } },
        viewport: { x: 20, y: 30, zoom: 0.8 },
      }),
    }));
    return <div aria-label="Citation graph">Graph canvas</div>;
  },
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

beforeEach(() => {
  window.localStorage.clear();
  vi.clearAllMocks();
});

describe("ResearchWorkspace", () => {
  it("saves and reopens a named graph with filters after a reload without another graph request", async () => {
    const first = render(<ResearchWorkspace />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "Synthetic lookup" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Explore" }));
    fireEvent.click(
      await screen.findByRole("button", { name: /Fixture paper/ }),
    );
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Save graph" })).toBeEnabled(),
    );
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    fireEvent.change(screen.getByLabelText("Citation direction"), {
      target: { value: "references" },
    });
    fireEvent.change(screen.getByLabelText("Publication year"), {
      target: { value: "2020" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save graph" }));
    const library = screen.getByRole("complementary", {
      name: "Saved graphs and recent searches",
    });
    fireEvent.change(within(library).getByLabelText("Graph name"), {
      target: { value: "My paper map" },
    });
    fireEvent.click(
      within(library).getByRole("button", { name: "Save graph" }),
    );
    expect(within(library).getByRole("status")).toHaveTextContent(
      "Saved “My paper map”",
    );
    const stored = JSON.parse(window.localStorage.getItem(SAVED_GRAPHS_KEY)!);
    expect(stored.items[0].layout.positions.W1).toEqual({ x: 150, y: -20 });
    first.unmount();
    vi.mocked(api.neighbors).mockClear();
    render(<ResearchWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: "Saved & recent" }));
    fireEvent.click(
      screen.getByRole("button", { name: "Open saved graph My paper map" }),
    );
    expect(api.neighbors).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Details" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Filters" }));
    expect(screen.getByLabelText("Citation direction")).toHaveValue(
      "references",
    );
    expect(screen.getByLabelText("Publication year")).toHaveValue(2020);
  });

  it("shows recent searches after a reload and reruns or clears them", async () => {
    const first = render(<ResearchWorkspace />);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "Synthetic history query" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Explore" }));
    await screen.findByRole("button", { name: /Fixture paper/ });
    first.unmount();
    vi.mocked(api.search).mockClear();
    render(<ResearchWorkspace />);
    fireEvent.click(screen.getByRole("button", { name: "Saved & recent" }));
    fireEvent.click(
      screen.getByRole("button", {
        name: "Search again for Synthetic history query",
      }),
    );
    expect(api.search).toHaveBeenCalledWith(
      "Synthetic history query",
      expect.any(AbortSignal),
    );
    await screen.findByRole("button", { name: /Fixture paper/ });
    fireEvent.click(screen.getByRole("button", { name: "Saved & recent" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
    expect(
      screen.queryByRole("button", { name: /Search again for/ }),
    ).toBeNull();
  });
});
