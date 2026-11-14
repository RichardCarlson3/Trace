import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TraceExperience } from "@/components/story/trace-experience";

vi.mock("@/components/layout/research-workspace", () => ({
  ResearchWorkspace: ({ onHome }: { onHome: () => void }) => (
    <main>
      <p>Research graph workspace</p>
      <button onClick={onHome}>TRACE home</button>
    </main>
  ),
}));

beforeEach(() => {
  vi.stubGlobal(
    "ResizeObserver",
    class {
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  );
  vi.stubGlobal("matchMedia", () => ({
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.spyOn(window, "scrollTo").mockImplementation(() => {});
});
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("TRACE scroll story", () => {
  it("offers a direct path to the graph and a route back to the story", async () => {
    render(<TraceExperience />);
    expect(
      screen.getByText("Past. Present. Future. One map."),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Explore now/ }));
    await waitFor(() =>
      expect(screen.queryByText("Past. Present. Future. One map.")).toBeNull(),
    );
    expect(screen.getByText("Research graph workspace")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "TRACE home" }));
    expect(
      await screen.findByText("Past. Present. Future. One map."),
    ).toBeInTheDocument();
    await waitFor(() => expect(window.scrollTo).toHaveBeenCalled());
  });
});
