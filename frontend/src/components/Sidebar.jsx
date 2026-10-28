import { useState, useRef, useEffect } from "react";
import { MenuIcon, SettingsIcon } from "./icons.jsx";
import { api } from "../api.js";
import { useT } from "../i18n.js";

const WIDTH_KEY = "calivi_sidebar_width";

const CHAT_GROUPS = [
  { id: "pinned", label: "Pinned" },
  { id: "day", label: "Last 24 hours" },
  { id: "week", label: "Last 7 days" },
  { id: "month", label: "Last 30 days" },
  { id: "older", label: "Older" },
  { id: "archived", label: "Archived" },
];

const DAY_MS = 24 * 60 * 60 * 1000;

function chatGroup(chat, now) {
  if (chat.archived) return "archived";
  if (chat.pinned) return "pinned";

  const timestamp = Date.parse(chat.updated_at || chat.created_at || "");
  if (!Number.isFinite(timestamp)) return "older";

  const age = Math.max(0, now - timestamp);
  if (age < DAY_MS) return "day";
  if (age < 7 * DAY_MS) return "week";
  if (age < 30 * DAY_MS) return "month";
  return "older";
}

export default function Sidebar({
  mobile = false, // phone layout (#61): full-width list with its own header, no resize handle
  onOpenSettings,
  chats,
  activeChatId,
  onSelectChat,
  onSearchResult,
  onNewChat,
  onDeleteChat,
  onBulkDeleteChats,
  onBulkArchiveChats,
  onRenameChat,
  onTogglePin,
  onCopyChat,
  me,
  onLogout,
}) {
  const t = useT();
  const [width, setWidth] = useState(() => Number(localStorage.getItem(WIDTH_KEY)) || 256);
  const [menu, setMenu] = useState(null); // { id, x, y }
  const [copied, setCopied] = useState(false);
  const [renamingId, setRenamingId] = useState(null);
  const [renameValue, setRenameValue] = useState("");
  const [expandedGroups, setExpandedGroups] = useState(() => ({ day: true }));
  const [now, setNow] = useState(() => Date.now());
  const [selectionMode, setSelectionMode] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState([]);
  const [searchTotal, setSearchTotal] = useState(0);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState("");
  const searchInputRef = useRef(null);
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const [bulkArchiving, setBulkArchiving] = useState(false);
  const [chatListStale, setChatListStale] = useState(false);
  const [bulkDeleteError, setBulkDeleteError] = useState("");
  const draggingRef = useRef(false);
  useEffect(() => {
    if (searchOpen) searchInputRef.current?.focus();
  }, [searchOpen]);
  useEffect(() => {
    if (!searchOpen || !searchQuery.trim()) {
      setSearchResults([]);
      setSearchTotal(0);
      setSearchLoading(false);
      setSearchError("");
      return;
    }
    const controller = new AbortController();
    setSearchLoading(true);
    setSearchError("");
    setSearchResults([]);
    setSearchTotal(0);
    const timer = setTimeout(async () => {
      try {
        const data = await api.searchMessages(searchQuery.trim(), { signal: controller.signal });
        if (controller.signal.aborted) return;
        if (!data || !Array.isArray(data.results) || !Number.isInteger(data.total)) {
          throw new Error("Invalid search response");
        }
        setSearchResults(data.results);
        setSearchTotal(data.total);
      } catch (error) {
        if (controller.signal.aborted) return;
        setSearchError("Search failed. Please try again.");
      } finally {
        if (!controller.signal.aborted) setSearchLoading(false);
      }
    }, 250);
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [searchOpen, searchQuery]);

  // Drag to resize the width
  useEffect(() => {
    function onMove(e) {
      if (!draggingRef.current) return;
      setWidth(Math.min(480, Math.max(200, e.clientX)));
    }
    function onUp() {
      draggingRef.current = false;
    }
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
    return () => {
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
  }, []);

  useEffect(() => {
    localStorage.setItem(WIDTH_KEY, String(width));
  }, [width]);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 60_000);
    return () => clearInterval(timer);
  }, []);

  const groupedChats = Object.fromEntries(CHAT_GROUPS.map((group) => [group.id, []]));
  for (const chat of chats) {
    groupedChats[chatGroup(chat, now)].push(chat);
  }

  for (const group of CHAT_GROUPS) {
    groupedChats[group.id].sort((a, b) => {
      const aTime = Date.parse(a.updated_at || a.created_at || "") || 0;
      const bTime = Date.parse(b.updated_at || b.created_at || "") || 0;
      return bTime - aTime;
    });
  }


  const menuChat = menu ? chats.find((c) => c.id === menu.id) : null;
  const selectedChats = chats.filter(chat => selectedIds.has(chat.id));
  const canArchive = selectedChats.some(chat => !chat.archived);
  const canUnarchive = selectedChats.some(chat => !!chat.archived);

  function toggleSelection(id) {
    setSelectedIds((previous) => {
      const next = new Set(previous);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleGroupSelection(items) {
    const ids = items.map((chat) => chat.id);
    setSelectedIds((previous) => {
      const next = new Set(previous);
      const allSelected = ids.every((id) => next.has(id));
      for (const id of ids) {
        if (allSelected) next.delete(id);
        else next.add(id);
      }
      return next;
    });
  }

  function cancelSelection() {
    if (bulkDeleting || bulkArchiving) return;
    setSelectionMode(false);
    setSelectedIds(new Set());
  }

  async function executeBulkDelete() {
    if (bulkDeleting || bulkArchiving || chatListStale || !confirmBulkDelete || selectedIds.size === 0) return;

    const ids = [...selectedIds];
    setBulkDeleting(true);
    setBulkDeleteError("");

    try {
      const failedIds = await onBulkDeleteChats(ids);
      if (!Array.isArray(failedIds)) {
        throw new Error("Invalid bulk-delete response");
      }

      if (failedIds.length === 0) {
        setConfirmBulkDelete(false);
        cancelSelection();
      } else {
        setSelectedIds(new Set(failedIds));
        setConfirmBulkDelete(false);
        setBulkDeleteError(
          `${failedIds.length} of ${ids.length} conversations could not be deleted.`
        );
      }
    } catch (error) {
      console.error("Bulk deletion failed", error);
      setConfirmBulkDelete(false);
      setBulkDeleteError(
        "Deletion could not be completed. Refresh the chat list before retrying."
      );
    } finally {
      setBulkDeleting(false);
    }
  }

  async function executeBulkArchive(archived) {
    if (bulkDeleting || bulkArchiving || chatListStale || confirmBulkDelete) return;

    const ids = chats
      .filter(chat => selectedIds.has(chat.id) && !!chat.archived !== archived)
      .map(chat => chat.id);

    if (!ids.length) return;

    setBulkArchiving(true);
    setBulkDeleteError("");

    try {
      const result = await onBulkArchiveChats(ids, archived);
      if (
        !result ||
        !Array.isArray(result.failedIds) ||
        typeof result.refreshFailed !== "boolean"
      ) {
        throw new Error("Invalid bulk-archive response");
      }

      const { failedIds, refreshFailed } = result;
      if (refreshFailed) setChatListStale(true);

      if (failedIds.length === 0 && !refreshFailed) {
        setSelectedIds(new Set());
        setSelectionMode(false);
        return;
      }

      const failed = new Set(failedIds);
      setSelectedIds(previous => {
        const next = new Set(previous);
        for (const id of ids) {
          if (!failed.has(id)) next.delete(id);
        }
        return next;
      });

      const failureMessage = failedIds.length
        ? `${failedIds.length} of ${ids.length} conversations could not be ${archived ? "archived" : "unarchived"}.`
        : "";

      setBulkDeleteError(
        [
          failureMessage,
          refreshFailed ? "Chat list could not be refreshed. Reload before making further changes." : "",
        ].filter(Boolean).join(" ")
      );
    } catch (error) {
      console.error("Bulk archive operation failed", error);
      setBulkDeleteError(
        "Archive operation could not be completed. Refresh the chat list before retrying."
      );
    } finally {
      setBulkArchiving(false);
    }
  }

  useEffect(() => {
    const available = new Set(chats.map(chat => chat.id));
    setSelectedIds(previous => {
      if ([...previous].every(id => available.has(id))) return previous;
      return new Set([...previous].filter(id => available.has(id)));
    });
  }, [chats]);


  function openMenu(e, id) {
    e.stopPropagation();
    const r = e.currentTarget.getBoundingClientRect();
    setCopied(false);
    setMenu({ id, x: r.right, y: r.bottom + 4 });
  }

  async function archiveSingleChat(id, archived) {
    if (bulkDeleting || bulkArchiving || chatListStale || confirmBulkDelete) return;

    setMenu(null);
    setBulkArchiving(true);
    setBulkDeleteError("");

    try {
      const result = await onBulkArchiveChats([id], archived);

      if (
        !result ||
        !Array.isArray(result.failedIds) ||
        typeof result.refreshFailed !== "boolean"
      ) {
        throw new Error("Invalid archive response");
      }

      if (result.refreshFailed) setChatListStale(true);

      const messages = [];
      if (result.failedIds.length) {
        messages.push(
          `Conversation could not be ${archived ? "archived" : "unarchived"}.`
        );
      }
      if (result.refreshFailed) {
        messages.push(
          "Chat list could not be refreshed. Reload before making further changes."
        );
      }

      setBulkDeleteError(messages.join(" "));
    } catch (error) {
      console.error("Single-chat archive operation failed", error);
      setChatListStale(true);
      setBulkDeleteError(
        "Archive operation could not be completed. Reload before retrying."
      );
    } finally {
      setBulkArchiving(false);
    }
  }

  function startRename(id) {
    const c = chats.find((x) => x.id === id);
    setRenamingId(id);
    setRenameValue(c?.title || "");
    setMenu(null);
  }

  function commitRename() {
    if (renamingId != null) {
      const v = renameValue.trim();
      const c = chats.find((x) => x.id === renamingId);
      if (v && c && v !== c.title) onRenameChat(renamingId, v);
    }
    setRenamingId(null);
  }

  return (
    <div
      className={`relative shrink-0 bg-neutral-900 flex flex-col h-dvh ${mobile ? "w-full" : ""}`}
      style={mobile ? undefined : { width }}
    >
      {mobile ? (
        <div className="flex items-center gap-2 px-4 pt-4 pb-2">
          <div className="flex-1 text-lg font-semibold text-neutral-100">Max</div>
          <button
            onClick={onNewChat}
            title={t("sidebar.newChat")}
            className="w-10 h-10 rounded-full bg-neutral-800 hover:bg-neutral-700 text-xl leading-none"
          >
            +
          </button>
          <button
            onClick={onOpenSettings}
            title={t("common.settings")}
            className="w-10 h-10 rounded-full bg-neutral-800 hover:bg-neutral-700 flex items-center justify-center text-neutral-300"
          >
            <SettingsIcon className="w-5 h-5" />
          </button>
        </div>
      ) : (
        <div className="p-3">
          <button
            onClick={onNewChat}
            className="w-full px-3 py-2 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-sm text-left transition-colors"
          >
            {t("sidebar.newChat")}
          </button>
        </div>
      )}

      <div className="shrink-0 px-3 pb-2" inert={bulkDeleting || bulkArchiving || chatListStale ? "" : undefined}>
        <div className="flex items-center gap-2 mb-2">
          <button type="button"
            aria-label="Search"
            aria-pressed={searchOpen}
            aria-expanded={searchOpen}
            onClick={() => {
              setSearchOpen(previous => !previous);
              if (searchOpen) setSearchQuery("");
            }}
            className={`px-3 py-1.5 text-sm font-semibold text-neutral-200 max-select-button border-solid border-current rounded-lg bg-transparent hover:bg-neutral-800 transition-colors ${searchOpen ? "border-2" : "border"}`}>
            Search
          </button>
          <button type="button"
            aria-label="Select"
            aria-pressed={selectionMode}
            onClick={() => {
              if (bulkDeleting || bulkArchiving || chatListStale) return;
              if (selectionMode) {
                cancelSelection();
              } else {
                setMenu(null);
                setRenamingId(null);
                setSelectionMode(true);
              }
            }}
            className={`px-3 py-1.5 text-sm font-semibold text-neutral-200 max-select-button border-solid border-current rounded-lg bg-transparent hover:bg-neutral-800 transition-colors ${selectionMode ? "border-2" : "border"}`}>
            Select
          </button>
        </div>
        {selectionMode && (
          <div className="flex flex-wrap items-center gap-x-3 gap-y-2 text-sm text-neutral-200">
            <span className="font-semibold">{selectedIds.size} selected</span>
            <button type="button"
              onClick={() => setSelectedIds(new Set(chats.map(c => c.id)))}
              className="ml-auto px-2 py-1 rounded hover:bg-neutral-800">
              Select all
            </button>
            {canUnarchive && (
              <button type="button"
                disabled={bulkArchiving}
                onClick={() => executeBulkArchive(false)}
                className="px-2 py-1 rounded hover:bg-neutral-800 disabled:opacity-40">
                {bulkArchiving ? "Working…" : "Unarchive selected"}
              </button>
            )}
            <button type="button"
              disabled={selectedIds.size === 0 || bulkDeleting || bulkArchiving}
              onClick={() => {
                setBulkDeleteError("");
                setConfirmBulkDelete(true);
              }}
              className="px-2 py-1 rounded text-red-400 hover:bg-red-950/40 disabled:opacity-40 disabled:cursor-not-allowed">
              Delete selected
            </button>
            {canArchive && (
              <button type="button"
                disabled={bulkArchiving}
                onClick={() => executeBulkArchive(true)}
                className="px-2 py-1 rounded hover:bg-neutral-800 disabled:opacity-40">
                {bulkArchiving ? "Working…" : "Archive selected"}
              </button>
            )}
          </div>
        )}
      </div>

      {searchOpen && (
        <div className="shrink-0 px-3 pb-2 flex items-center gap-2">
          <input ref={searchInputRef} type="search" aria-label="Search conversations"
            value={searchQuery}
            onChange={(event) => setSearchQuery(event.target.value)}
            placeholder="Search conversations…"
            className="min-w-0 flex-1 rounded-lg border border-solid border-current bg-neutral-900 px-3 py-1.5 text-sm text-neutral-100 outline-none focus:ring-1 focus:ring-neutral-300" />
        </div>
      )}
      {searchOpen && searchQuery.trim() && (
        <div aria-label="Search results" className="shrink-0 px-3 pb-2 max-h-[40vh] overflow-y-auto themed-scroll space-y-1">
          {searchLoading && <p role="status" className="text-sm text-neutral-400">Searching…</p>}
          {searchError && <p role="alert" className="text-sm text-red-400">{searchError}</p>}
          {!searchLoading && !searchError && (
            <>
              <p className="text-xs text-neutral-400">{searchTotal} matching messages{searchTotal > searchResults.length ? ` (showing ${searchResults.length})` : ""}</p>
              {searchResults.map((result) => (
                <button key={result.message_id} type="button"
                  aria-label={`Open search result from ${result.chat_title || "Untitled conversation"}`}
                  onClick={() => onSearchResult(result.chat_id, result.message_id)}
                  className="w-full rounded-lg p-2 text-left text-sm text-neutral-200 hover:bg-neutral-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-neutral-300">
                  <span className="block truncate font-semibold">{result.chat_title || "Untitled conversation"}</span>
                  <span className="block text-xs text-neutral-400 line-clamp-3 break-words">{String(result.content || "").slice(0, 240)}</span>
                  <span className="block text-xs text-neutral-500">{result.role === "user" ? "You" : "Assistant"}{result.archived ? " · Archived" : ""}</span>
                </button>
              ))}
            </>
          )}
        </div>
      )}
      {searchOpen && searchQuery.trim() && (
        <div role="separator" aria-label="Search results divider"
          className="shrink-0 mx-3 my-2 border-t border-solid border-neutral-600" />
      )}
      {bulkDeleteError && (
        <div role="alert" className="shrink-0 px-3 pb-2 text-sm text-red-400">
          {bulkDeleteError}
        </div>
      )}

      {searchOpen && searchQuery.trim() && (
        <div aria-hidden="true" className="shrink-0 mx-3 my-2 h-px bg-neutral-500/70" />
      )}
      <div className="flex-1 overflow-y-auto themed-scroll px-3 space-y-1" inert={bulkDeleting || bulkArchiving || chatListStale ? "" : undefined}>
        {CHAT_GROUPS.map((group) => {
          const items = groupedChats[group.id];
          if (!items.length) return null;

          const expanded = !!expandedGroups[group.id];
          const selectedCount = items.filter(chat => selectedIds.has(chat.id)).length;

          return (
            <div key={group.id}>
              <div className="flex items-center">
                {selectionMode && (
                  <input
                    type="checkbox"
                    aria-label={`Select all in ${group.label}`}
                    checked={selectedCount === items.length}
                    ref={node => {
                      if (node) node.indeterminate =
                        selectedCount > 0 && selectedCount < items.length;
                    }}
                    onChange={() => toggleGroupSelection(items)}
                    className="ml-3 shrink-0 w-4 h-4 accent-blue-500"
                  />
                )}
              <button
                type="button"
                aria-expanded={expanded}
                onClick={() => setExpandedGroups((previous) => ({
                  ...previous,
                  [group.id]: !expanded,
                }))}
                className={`w-full flex items-center gap-2 px-3 py-2 font-bold italic text-neutral-300 hover:text-neutral-100 ${mobile ? "text-base" : "text-sm"}`}
              >
                <span className="w-3 text-center">{expanded ? "▾" : "▸"}</span>
                <span>{group.label}</span>
                <span className="ml-auto font-normal text-neutral-500">{items.length}</span>
              </button>
              </div>

              {expanded && items.map((chat) => (
          <div
            key={chat.id}
            onClick={() => selectionMode ? toggleSelection(chat.id) : renamingId !== chat.id && onSelectChat(chat.id)}
            className={`group flex items-center gap-1.5 px-3 rounded-lg cursor-pointer ${mobile ? "py-3.5 text-base" : "py-2 text-sm"} ${
              chat.id === activeChatId ? "bg-neutral-800" : "hover:bg-neutral-800/60"
            }`}
          >
            {selectionMode && (
              <input
                type="checkbox"
                aria-label={`Select ${chat.title}`}
                checked={selectedIds.has(chat.id)}
                onChange={() => toggleSelection(chat.id)}
                onClick={e => e.stopPropagation()}
                className="shrink-0 w-4 h-4 accent-blue-500"
              />
            )}
            {chat.pinned && (
              <svg
                width="14"
                height="14"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="shrink-0"
              >
                <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
                <path d="M7 11V7a5 5 0 0 1 10 0v4" />
              </svg>
            )}
            {renamingId === chat.id ? (
              <input
                autoFocus
                value={renameValue}
                onChange={(e) => setRenameValue(e.target.value)}
                onClick={(e) => e.stopPropagation()}
                onKeyDown={(e) => {
                  if (e.key === "Enter") commitRename();
                  else if (e.key === "Escape") setRenamingId(null);
                }}
                onBlur={commitRename}
                className="flex-1 min-w-0 bg-neutral-950 rounded px-1.5 py-0.5 outline-none"
              />
            ) : (
              <span className="flex-1 truncate">{chat.title}</span>
            )}
            {!selectionMode && <button
              onClick={(e) => openMenu(e, chat.id)}
              className={`opacity-0 group-hover:opacity-100 [@media(hover:none)]:opacity-100 shrink-0 hover:bg-neutral-700 rounded text-neutral-300 ${mobile ? "p-2 -mr-2" : "p-0.5"}`}
              title={t("sidebar.menu")}
            >
              <MenuIcon className="w-4 h-4" />
            </button>}
          </div>
              ))}
            </div>
          );
        })}
      </div>

      {/* User + sign out (bottom) */}
      {me && (
        <div className="shrink-0 flex items-center gap-2 px-3 py-2.5 text-sm border-t border-white/5">
          <div className="min-w-0 flex-1">
            <div className="truncate text-neutral-200">{me.username}</div>
            <div className="text-xs text-neutral-500">
              #{String(me.id).padStart(4, "0")}
              {me.role === "admin" && ` · ${me.id === 1 ? t("users.superAdmin") : t("users.roleAdmin")}`}
            </div>
          </div>
          <button
            onClick={onLogout}
            title={t("auth.logout")}
            className="shrink-0 text-neutral-500 hover:text-red-400 px-2 py-1 rounded text-xl leading-none"
          >
            ⎋
          </button>
        </div>
      )}

      {/* Width resize handle (right edge) */}
      {!mobile && (
        <div
          onMouseDown={() => (draggingRef.current = true)}
          className="absolute top-0 right-0 h-full w-1.5 cursor-col-resize hover:bg-neutral-700/70"
        />
      )}

      {menu && menuChat && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setMenu(null)} />
          <div
            className="fixed z-50 -translate-x-full bg-neutral-800 rounded-lg py-1 text-sm shadow-xl min-w-[180px]"
            style={{ top: menu.y, left: menu.x }}
          >
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-neutral-700"
              onClick={() => startRename(menu.id)}
            >
              {t("sidebar.rename")}
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-neutral-700"
              onClick={() => {
                onTogglePin(menu.id, !menuChat.pinned);
                setMenu(null);
              }}
            >
              {menuChat.pinned ? t("sidebar.unpin") : t("sidebar.pin")}
            </button>
            <button
              type="button"
              className="block w-full text-left px-3 py-1.5 hover:bg-neutral-700"
              onClick={() => archiveSingleChat(menu.id, !menuChat.archived)}
            >
              {menuChat.archived ? "Unarchive" : "Archive"}
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-neutral-700"
              onClick={async () => {
                await onCopyChat(menu.id);
                setCopied(true);
                setTimeout(() => {
                  setCopied(false);
                  setMenu(null);
                }, 900);
              }}
            >
              {copied ? <span className="text-green-400">{t("common.copied")}</span> : t("common.copy")}
            </button>
            <button
              className="block w-full text-left px-3 py-1.5 hover:bg-neutral-700 text-red-400"
              onClick={() => {
                onDeleteChat(menu.id);
                setMenu(null);
              }}
            >
              {t("common.delete")}
            </button>
          </div>
        </>
      )}

      {confirmBulkDelete && (
        <div
          className="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 px-4"
        >
          <div
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="bulk-delete-title"
            aria-describedby="bulk-delete-description"
            className="w-full max-w-sm rounded-xl bg-neutral-900 p-5 text-neutral-100 shadow-2xl"
          >
            <h2 id="bulk-delete-title" className="text-lg font-bold">
              Delete conversations?
            </h2>
            <p id="bulk-delete-description" className="mt-3 text-sm text-neutral-300">
              Permanently delete {selectedIds.size} selected
              {selectedIds.size === 1 ? " conversation" : " conversations"}?
              This cannot be undone.
            </p>

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                disabled={bulkDeleting}
                onClick={() => setConfirmBulkDelete(false)}
                className="rounded-lg px-3 py-2 text-sm hover:bg-neutral-700 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={bulkDeleting}
                onClick={executeBulkDelete}
                className="rounded-lg bg-red-700 px-3 py-2 text-sm font-semibold text-white hover:bg-red-600 disabled:opacity-50"
              >
                {bulkDeleting ? "Deleting…" : "Delete permanently"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
