import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { CitationCanvas } from "@/components/graph/citation-canvas";

vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

describe("actual React Flow canvas", () => {
  it("initializes the viewport, background and zoom controls", () => {
    const { container } = render(
      <CitationCanvas paper={null} onSelect={() => {}} />,
    );
    expect(
      container.querySelector(".react-flow__viewport"),
    ).toBeInTheDocument();
    expect(
      container.querySelector(".react-flow__background"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /zoom in/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("Follow the connections.")).toBeInTheDocument();
  });
});
