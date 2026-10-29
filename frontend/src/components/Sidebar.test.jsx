import { render, screen, fireEvent, act, cleanup } from "@testing-library/react";
import { beforeEach, afterEach, describe, expect, test, vi } from "vitest";
import Sidebar from "./Sidebar.jsx";

vi.mock("../i18n.js", () => ({
  useT: () => (key) => key,
}));

const NOW = Date.parse("2026-10-16T12:00:00.000Z");
const DAY = 24 * 60 * 60 * 1000;

function chat(id, ageDays, pinned = false) {
  return {
    id,
    title: `Chat ${id}`,
    pinned,
    updated_at: new Date(NOW - ageDays * DAY).toISOString(),
  };
}

function mount(chats, activeChatId = null) {
  const props = {
    chats,
    activeChatId,
    mobile: false,
    onSelectChat: vi.fn(),
    onSearchResult: vi.fn(),
    onNewChat: vi.fn(),
    onDeleteChat: vi.fn(),
    onBulkDeleteChats: vi.fn().mockResolvedValue([]),
    onBulkArchiveChats: vi.fn().mockResolvedValue({ failedIds: [], refreshFailed: false }),
    onRenameChat: vi.fn(),
    onTogglePin: vi.fn(),
    onCopyChat: vi.fn(),
  };

  const view = render(<Sidebar {...props} />);

  return {
    ...view,
    props,
    update(next = {}) {
      Object.assign(props, next);
      view.rerender(<Sidebar {...props} />);
    },
  };
}

function heading(label) {
  return screen.getByRole("button", { name: new RegExp(`^[▸▾]\\s+${label}\\s+\\d+$`) });
}

function expanded(label) {
  return heading(label).getAttribute("aria-expanded") === "true";
}

beforeEach(() => {
  vi.useFakeTimers();
  vi.setSystemTime(NOW);
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("Sidebar archived conversations", () => {
  test("archived chats appear only in Archived, regardless of age or pin", () => {
    const recent = { ...chat(1, 0.1, true), archived: true };
    const old = { ...chat(2, 45), archived: true };

    mount([recent, old, chat(3, 0.1)]);

    expect(expanded("Archived")).toBe(false);
    expect(heading("Archived").textContent).toContain("2");
    expect(screen.queryByRole("button", {
      name: /^[▸▾]\\s+Pinned\\s+\\d+$/,
    })).toBeNull();

    expect(heading("Last 24 hours").textContent).toContain("1");

    fireEvent.click(heading("Archived"));

    expect(screen.getByText("Chat 1")).toBeTruthy();
    expect(screen.getByText("Chat 2")).toBeTruthy();
    expect(expanded("Archived")).toBe(true);
  });

  test("selecting the collapsed Archived group does not expand it", () => {
    mount([
      { ...chat(1, 0.1), archived: true },
      { ...chat(2, 40), archived: true },
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));

    const checkbox = screen.getByRole("checkbox", {
      name: "Select all in Archived",
    });

    fireEvent.click(checkbox);

    expect(checkbox.checked).toBe(true);
    expect(screen.getByText("2 selected")).toBeTruthy();
    expect(expanded("Archived")).toBe(false);
  });

  test("activating an archived chat leaves Archived collapsed", () => {
    const archived = { ...chat(1, 40), archived: true };
    const view = mount([archived]);

    expect(expanded("Archived")).toBe(false);

    act(() => view.update({ activeChatId: 1 }));

    expect(expanded("Archived")).toBe(false);
    expect(screen.queryByText("Chat 1")).toBeNull();

    fireEvent.click(heading("Archived"));
    expect(expanded("Archived")).toBe(true);
    expect(screen.getByText("Chat 1")).toBeTruthy();
  });
});

describe("Sidebar multi-selection", () => {
  test("selects a group and permits individual deselection", () => {
    mount([chat(1, 0.1), chat(2, 0.2)]);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));

    const group = screen.getByRole("checkbox", {
      name: "Select all in Last 24 hours",
    });

    fireEvent.click(group);
    expect(group.checked).toBe(true);
    expect(screen.getByText("2 selected")).toBeTruthy();

    fireEvent.click(screen.getByRole("checkbox", {
      name: "Select Chat 1",
    }));

    expect(group.checked).toBe(false);
    expect(group.indeterminate).toBe(true);
    expect(screen.getByText("1 selected")).toBeTruthy();
  });
});

describe("Sidebar bulk archiving", () => {
  test("reports a failed refresh separately from successful archive requests", async () => {
    const view = mount([chat(1, 0.1), chat(2, 0.2)]);
    view.props.onBulkArchiveChats.mockResolvedValue({
      failedIds: [2],
      refreshFailed: true,
    });

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Archive selected" }));
    });

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([1, 2], true);
    expect(screen.getByText("1 selected")).toBeTruthy();
    expect(screen.getByRole("alert").textContent)
      .toContain("Chat list could not be refreshed");
    expect(screen.getByRole("alert").textContent)
      .toContain("1 of 2 conversations could not be archived");

    // The selection toolbar must be inert until reload.
    const toolbar = screen.getByRole("button", {
      name: "Select all",
    }).closest("[inert]");

    expect(toolbar).not.toBeNull();
    expect(toolbar.hasAttribute("inert")).toBe(true);

    // Even a programmatically dispatched click cannot bypass the handler guard.
    fireEvent.click(screen.getByRole("button", {
      name: "Archive selected",
      hidden: true,
    }));

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledTimes(1);
  });

  test("locks selection controls while archiving is pending", async () => {
    let finishArchive;
    const pending = new Promise(resolve => {
      finishArchive = resolve;
    });

    const view = mount([chat(1, 0.1), chat(2, 0.2)]);
    view.props.onBulkArchiveChats.mockReturnValue(pending);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));

    fireEvent.click(screen.getByRole("button", { name: "Archive selected" }));

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledTimes(1);
    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([1, 2], true);
    expect(screen.getByRole("button", { name: "Working…" }).disabled).toBe(true);

    // A second submission must not start another operation.
    fireEvent.click(screen.getByRole("button", { name: "Working…" }));
    expect(view.props.onBulkArchiveChats).toHaveBeenCalledTimes(1);

    await act(async () => {
      finishArchive({ failedIds: [], refreshFailed: false });
      await pending;
    });

    expect(screen.getByRole("button", { name: "Select" })).toBeTruthy();
    expect(screen.queryByText("0 selected")).toBeNull();
    expect(screen.queryByRole("button", { name: "Working…" })).toBeNull();
  });

  test("partial archive failure retains only failed IDs for retry", async () => {
    const view = mount([chat(1, 0.1), chat(2, 0.2)]);
    view.props.onBulkArchiveChats.mockResolvedValue({ failedIds: [2], refreshFailed: false });

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Archive selected" }));
    });

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([1, 2], true);
    expect(screen.getByText("1 selected")).toBeTruthy();
    expect(screen.getByText(/1 of 2 conversations could not be archived/))
      .toBeTruthy();

    expect(screen.getByRole("checkbox", {
      name: "Select Chat 1",
    }).checked).toBe(false);

    expect(screen.getByRole("checkbox", {
      name: "Select Chat 2",
    }).checked).toBe(true);
  });

  test("mixed selections archive and unarchive only eligible chats", async () => {
    const view = mount([
      chat(1, 0.1),
      { ...chat(2, 2), archived: true },
      chat(3, 0.2),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));

    expect(screen.getByRole("button", { name: "Archive selected" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Unarchive selected" })).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Archive selected" }));
    });

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([1, 3], true);
    expect(screen.getByRole("button", { name: "Select" })).toBeTruthy();
    expect(screen.queryByText("1 selected")).toBeNull();

    // A new operation requires explicitly entering selection mode again.
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Unarchive selected" }));
    });

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([2], false);
    expect(view.props.onBulkArchiveChats).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "Select" })).toBeTruthy();
    expect(screen.queryByText("0 selected")).toBeNull();
  });
});

describe("Sidebar individual archive menu", () => {
  function openChatMenu(title) {
    const row = screen.getByText(title).closest(".group");
    expect(row).not.toBeNull();
    fireEvent.click(row.querySelector('button[title="sidebar.menu"]'));
  }

  test("archives a normal chat and closes the menu", async () => {
    const view = mount([chat(1, 0.1)]);

    openChatMenu("Chat 1");
    expect(screen.getByRole("button", { name: "Archive" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Unarchive" })).toBeNull();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    });

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([1], true);
    expect(screen.queryByRole("button", { name: "Archive" })).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  test("unarchives an archived chat", async () => {
    const view = mount([{ ...chat(2, 2), archived: true }]);

    fireEvent.click(heading("Archived"));
    openChatMenu("Chat 2");

    expect(screen.getByRole("button", { name: "Unarchive" })).toBeTruthy();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Unarchive" }));
    });

    expect(view.props.onBulkArchiveChats).toHaveBeenCalledWith([2], false);
    expect(screen.queryByRole("button", { name: "Unarchive" })).toBeNull();
  });

  test("reports an API failure without claiming success", async () => {
    const view = mount([chat(1, 0.1)]);
    view.props.onBulkArchiveChats.mockResolvedValue({
      failedIds: [1],
      refreshFailed: false,
    });

    openChatMenu("Chat 1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    });

    expect(screen.getByRole("alert").textContent)
      .toContain("Conversation could not be archived.");
    expect(screen.getByRole("button", { name: "Select" })).toBeTruthy();
  });

  test("locks chat controls after a failed refresh", async () => {
    const view = mount([chat(1, 0.1)]);
    view.props.onBulkArchiveChats.mockResolvedValue({
      failedIds: [],
      refreshFailed: true,
    });

    openChatMenu("Chat 1");

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Archive" }));
    });

    expect(screen.getByRole("alert").textContent)
      .toContain("Chat list could not be refreshed.");

    const select = screen.getByRole("button", {
      name: "Select",
      hidden: true,
    });

    expect(select.closest("[inert]")).not.toBeNull();

    fireEvent.click(select);
    expect(screen.queryByText("0 selected")).toBeNull();
  });
});

describe("Sidebar bulk deletion", () => {
  test("disables confirmation controls while deletion is pending", async () => {
    let finishDeletion;
    const pending = new Promise(resolve => {
      finishDeletion = resolve;
    });

    const view = mount([chat(1, 0.1)]);
    view.props.onBulkDeleteChats.mockReturnValue(pending);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Chat 1" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    fireEvent.click(screen.getByRole("button", { name: "Delete permanently" }));

    expect(view.props.onBulkDeleteChats).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Deleting…" }).disabled).toBe(true);
    expect(screen.getByRole("alertdialog").querySelectorAll("button:disabled").length).toBe(2);

    await act(async () => {
      finishDeletion([]);
      await pending;
    });

    expect(view.props.onBulkDeleteChats).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("alertdialog")).toBeNull();
  });

  test("partial failure retains only failed IDs for retry", async () => {
    const view = mount([chat(1, 0.1), chat(2, 0.2)]);
    view.props.onBulkDeleteChats.mockResolvedValue([2]);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {
        name: "Delete permanently",
      }));
    });

    expect(view.props.onBulkDeleteChats).toHaveBeenCalledWith([1, 2]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByText("1 selected")).toBeTruthy();
    expect(screen.getByText(/1 of 2 conversations could not be deleted/))
      .toBeTruthy();

    expect(screen.getByRole("checkbox", {
      name: "Select Chat 1",
    }).checked).toBe(false);

    expect(screen.getByRole("checkbox", {
      name: "Select Chat 2",
    }).checked).toBe(true);
  });

  test("confirmation deletes selected IDs and exits selection mode", async () => {
    const view = mount([chat(1, 0.1), chat(2, 0.2), chat(3, 0.3)]);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Chat 1" }));
    fireEvent.click(screen.getByRole("checkbox", { name: "Select Chat 3" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    expect(view.props.onBulkDeleteChats).not.toHaveBeenCalled();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", {
        name: "Delete permanently",
      }));
    });

    expect(view.props.onBulkDeleteChats).toHaveBeenCalledTimes(1);
    expect(view.props.onBulkDeleteChats).toHaveBeenCalledWith([1, 3]);
    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(screen.getByRole("button", { name: "Select" })).toBeTruthy();
    expect(screen.queryByText("2 selected")).toBeNull();
  });

  test("cancelling confirmation never deletes conversations", () => {
    const view = mount([chat(1, 0.1), chat(2, 0.2)]);

    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    expect(screen.getByRole("alertdialog")).toBeTruthy();
    expect(screen.getByText(/Permanently delete 2 selected conversations/))
      .toBeTruthy();

    expect(view.props.onBulkDeleteChats).not.toHaveBeenCalled();

    fireEvent.click(
      screen.getByRole("alertdialog")
        .querySelector("button:not([disabled])")
    );

    expect(screen.queryByRole("alertdialog")).toBeNull();
    expect(view.props.onBulkDeleteChats).not.toHaveBeenCalled();
    expect(screen.getByText("2 selected")).toBeTruthy();
  });
});

describe("Sidebar selection behaviour", () => {
  test("selects a collapsed group without expanding it", () => {
    mount([chat(1, 2), chat(2, 3)]);
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    const group = screen.getByRole("checkbox", {
      name: "Select all in Last 7 days",
    });
    fireEvent.click(group);
    expect(group.checked).toBe(true);
    expect(screen.getByText("2 selected")).toBeTruthy();
    expect(expanded("Last 7 days")).toBe(false);
  });

  test("Select all includes collapsed groups", () => {
    mount([chat(1, 0.1), chat(2, 2), chat(3, 40)]);
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("button", { name: "Select all" }));
    expect(screen.getByText("3 selected")).toBeTruthy();
    for (const label of ["Last 24 hours", "Last 7 days", "Older"]) {
      expect(screen.getByRole("checkbox", {
        name: `Select all in ${label}`,
      }).checked).toBe(true);
    }
  });

  test("Cancel clears selection", () => {
    mount([chat(1, 0.1)]);
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByRole("checkbox", {
      name: "Select Chat 1",
    }));
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.queryByText("1 selected")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    expect(screen.getByText("0 selected")).toBeTruthy();
  });

  test("mobile selection does not open conversations", () => {
    const view = mount([chat(1, 0.1)]);
    view.update({ mobile: true });
    fireEvent.click(screen.getByRole("button", { name: "Select" }));
    fireEvent.click(screen.getByText("Chat 1"));
    expect(screen.getByText("1 selected")).toBeTruthy();
    expect(view.props.onSelectChat).not.toHaveBeenCalled();
  });
});

describe("Sidebar chat accordions", () => {
  test("only Last 24 hours starts expanded", () => {
    mount([
      chat(1, 0.5),
      chat(2, 2),
      chat(3, 10),
      chat(4, 40),
      chat(5, 0.2, true),
    ]);

    expect(expanded("Pinned")).toBe(false);
    expect(expanded("Last 24 hours")).toBe(true);
    expect(expanded("Last 7 days")).toBe(false);
    expect(expanded("Last 30 days")).toBe(false);
    expect(expanded("Older")).toBe(false);
    expect(screen.getByText("Chat 1")).toBeTruthy();
    expect(screen.queryByText("Chat 2")).toBeNull();
  });

  test("age boundaries are exclusive and chats appear exactly once", () => {
    mount([
      chat(1, 0),
      chat(2, 1),
      chat(3, 7),
      chat(4, 30),
    ]);

    expect(heading("Last 24 hours").textContent).toContain("1");
    expect(heading("Last 7 days").textContent).toContain("1");
    expect(heading("Last 30 days").textContent).toContain("1");
    expect(heading("Older").textContent).toContain("1");

    for (const label of ["Last 7 days", "Last 30 days", "Older"]) {
      fireEvent.click(heading(label));
    }

    for (let id = 1; id <= 4; id++) {
      expect(screen.getAllByText(`Chat ${id}`)).toHaveLength(1);
    }
  });

  test("pinned chats appear only in Pinned", () => {
    mount([chat(1, 0.1, true), chat(2, 0.1)]);

    expect(heading("Pinned").textContent).toContain("1");
    expect(heading("Last 24 hours").textContent).toContain("1");

    fireEvent.click(heading("Pinned"));
    expect(screen.getAllByText("Chat 1")).toHaveLength(1);
    expect(screen.getAllByText("Chat 2")).toHaveLength(1);
  });

  test("manual accordion toggling works", () => {
    mount([chat(1, 0.1), chat(2, 2)]);

    fireEvent.click(heading("Last 24 hours"));
    expect(expanded("Last 24 hours")).toBe(false);
    expect(screen.queryByText("Chat 1")).toBeNull();

    fireEvent.click(heading("Last 7 days"));
    expect(expanded("Last 7 days")).toBe(true);
    expect(screen.getByText("Chat 2")).toBeTruthy();
  });

  test("changing active chat preserves manual accordion state", () => {
    const view = mount([chat(1, 2), chat(2, 10)]);

    act(() => view.update({ activeChatId: 1 }));
    expect(expanded("Last 7 days")).toBe(false);

    fireEvent.click(heading("Last 7 days"));
    expect(expanded("Last 7 days")).toBe(true);

    act(() => view.update({ activeChatId: 2 }));
    expect(expanded("Last 30 days")).toBe(false);
    expect(expanded("Last 7 days")).toBe(true);

    act(() => view.update({ activeChatId: 1 }));
    expect(expanded("Last 7 days")).toBe(true);
    expect(expanded("Last 30 days")).toBe(false);
  });

  test("moving an active chat between age groups does not expand them", () => {
    const view = mount([chat(1, 2)], 1);

    expect(expanded("Last 7 days")).toBe(false);

    fireEvent.click(heading("Last 7 days"));
    expect(expanded("Last 7 days")).toBe(true);

    act(() => view.update({ chats: [chat(1, 10)] }));

    expect(screen.queryByRole("button", {
      name: /^[▸▾]\\s+Last 7 days\\s+\\d+$/,
    })).toBeNull();
    expect(expanded("Last 30 days")).toBe(false);
    expect(screen.queryByText("Chat 1")).toBeNull();

    fireEvent.click(heading("Last 30 days"));
    expect(expanded("Last 30 days")).toBe(true);
    expect(screen.getByText("Chat 1")).toBeTruthy();
  });
});


describe("Sidebar search entry (step 1)", () => {
  test("Search matches Select styling and focuses the input immediately", () => {
    mount([chat(1, 0.1)]);
    const searchButton = screen.getByRole("button", { name: "Search" });
    const selectButton = screen.getByRole("button", { name: "Select" });
    expect(searchButton.className).toBe(selectButton.className);
    expect(screen.queryByRole("searchbox", { name: "Search conversations" })).toBeNull();
    fireEvent.click(searchButton);
    const input = screen.getByRole("searchbox", { name: "Search conversations" });
    expect(document.activeElement).toBe(input);
    expect(screen.getByText("Chat 1")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Search" }));
    expect(screen.queryByRole("searchbox", { name: "Search conversations" })).toBeNull();
    expect(screen.getByText("Chat 1")).toBeTruthy();
  });
});


describe("Sidebar search results (step 2)", () => {
  test("shows debounced results above conversation groups, then Search closes results and restores the list", async () => {
    const { api } = await import("../api.js");
    const spy = vi.spyOn(api, "searchMessages").mockResolvedValue({
      total: 1, results: [{ message_id: 42, chat_id: 1, chat_title: "Driver diagnostics", content: "CUDA driver failed", role: "user", archived: false }],
    });
    try {
      const view = mount([chat(1, 0.1)]);
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      fireEvent.change(screen.getByRole("searchbox", { name: "Search conversations" }), { target: { value: "CUDA" } });
      expect(spy).not.toHaveBeenCalled();
      await act(async () => { await vi.advanceTimersByTimeAsync(260); });
      expect(spy).toHaveBeenCalledWith("CUDA", expect.objectContaining({ signal: expect.any(Object) }));
      expect(screen.getByText("Driver diagnostics")).toBeTruthy();
      expect(screen.getByText("CUDA driver failed")).toBeTruthy();
      expect(screen.getByText("Chat 1")).toBeTruthy();
      fireEvent.click(screen.getByRole("button", { name: "Open search result from Driver diagnostics" }));
      expect(view.props.onSearchResult).toHaveBeenCalledWith(1, 42);
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      expect(screen.queryByLabelText("Search results")).toBeNull();
      expect(screen.getByText("Chat 1")).toBeTruthy();
    } finally { spy.mockRestore(); }
  });
  test("ignores a late response after closing search", async () => {
    const { api } = await import("../api.js");
    let resolveRequest;
    const spy = vi.spyOn(api, "searchMessages").mockImplementation(() => new Promise(resolve => { resolveRequest = resolve; }));
    try {
      mount([chat(1, 0.1)]);
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      fireEvent.change(screen.getByRole("searchbox", { name: "Search conversations" }), { target: { value: "CUDA" } });
      await act(async () => { await vi.advanceTimersByTimeAsync(260); });
      fireEvent.click(screen.getByRole("button", { name: "Search" }));
      await act(async () => { resolveRequest({ total: 1, results: [{ message_id: 9, chat_id: 1, chat_title: "Stale result", content: "late" }] }); });
      expect(screen.queryByText("Stale result")).toBeNull();
    } finally { spy.mockRestore(); }
  });
});
