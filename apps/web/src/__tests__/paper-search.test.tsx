import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useState } from "react";
import { PaperSearch } from "@/components/layout/paper-search";
import { useBrowserLibrary } from "@/hooks/use-browser-library";
import { RECENT_SEARCHES_KEY } from "@/lib/browser-library";

const search = vi.fn();
function SearchFixture() {
  const [query, setQuery] = useState("");
  const library = useBrowserLibrary();
  return (
    <>
      <PaperSearch
        query={query}
        onChange={setQuery}
        library={library}
        busy={false}
        onSubmit={(event) => {
          event.preventDefault();
          search(query);
        }}
        onSearch={search}
      />
      <button onClick={() => library.recordSearch("Synthetic new lookup")}>
        Record lookup
      </button>
    </>
  );
}

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
  // Synthetic history only, not research evidence.
  localStorage.setItem(
    RECENT_SEARCHES_KEY,
    JSON.stringify({
      version: 1,
      items: [
        { query: "Synthetic Graphs", searched_at: "2026-11-14T12:00:00Z" },
        {
          query: "Synthetic Neural Networks",
          searched_at: "2026-11-14T11:00:00Z",
        },
      ],
    }),
  );
});

describe("recent searches in the search field", () => {
  it("opens on focus, filters case-insensitively, and replays a selected query", () => {
    render(<SearchFixture />);
    expect(
      screen.queryByRole("region", { name: "Recent searches" }),
    ).toBeNull();
    fireEvent.focus(screen.getByRole("searchbox"));
    expect(
      screen.getAllByRole("button", { name: /Search again/ }),
    ).toHaveLength(2);
    fireEvent.change(screen.getByRole("searchbox"), {
      target: { value: "GRAPH" },
    });
    expect(
      screen.getAllByRole("button", { name: /Search again/ }),
    ).toHaveLength(1);
    fireEvent.click(
      screen.getByRole("button", { name: "Search again for Synthetic Graphs" }),
    );
    expect(search).toHaveBeenCalledWith("Synthetic Graphs");
    expect(
      screen.queryByRole("region", { name: "Recent searches" }),
    ).toBeNull();
  });

  it("supports arrow-key focus, Escape, and dismissing when focus leaves", () => {
    render(<SearchFixture />);
    const field = screen.getByRole("searchbox");
    act(() => field.focus());
    fireEvent.keyDown(field, { key: "ArrowDown" });
    const first = screen.getByRole("button", {
      name: "Search again for Synthetic Graphs",
    });
    expect(first).toHaveFocus();
    fireEvent.keyDown(first, { key: "ArrowDown" });
    const second = screen.getByRole("button", {
      name: "Search again for Synthetic Neural Networks",
    });
    expect(second).toHaveFocus();
    fireEvent.keyDown(second, { key: "Escape" });
    expect(field).toHaveFocus();
    expect(
      screen.queryByRole("region", { name: "Recent searches" }),
    ).toBeNull();
    fireEvent.keyDown(field, { key: "ArrowDown" });
    expect(
      screen.getByRole("button", { name: "Search again for Synthetic Graphs" }),
    ).toHaveFocus();
    act(() => screen.getByRole("button", { name: "Record lookup" }).focus());
    expect(
      screen.queryByRole("region", { name: "Recent searches" }),
    ).toBeNull();
  });

  it("clears history across mounts and reports corrupt history beside the field", () => {
    const first = render(<SearchFixture />);
    fireEvent.focus(screen.getByRole("searchbox"));
    fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
    first.unmount();
    render(<SearchFixture />);
    fireEvent.focus(screen.getByRole("searchbox"));
    expect(
      screen.queryByRole("region", { name: "Recent searches" }),
    ).toBeNull();
    act(() => {
      localStorage.setItem(RECENT_SEARCHES_KEY, "damaged");
      window.dispatchEvent(new Event("storage"));
    });
    expect(screen.getByRole("alert")).toHaveTextContent("Could not read");
    fireEvent.click(screen.getByRole("button", { name: "Clear history" }));
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
