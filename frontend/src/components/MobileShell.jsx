import React, { useState } from "react";
import ChatView from "./ChatView.jsx";
import SettingsModal from "./SettingsModal.jsx";

function titleForChat(chat) {
  return chat?.title || chat?.name || "New conversation";
}

function previewForChat(chat) {
  const value =
    chat?.last_message?.content ??
    chat?.lastMessage?.content ??
    chat?.preview ??
    "";

  return typeof value === "string"
    ? value.replace(/\s+/g, " ").trim()
    : "";
}

export default function MobileShell({
  chats,
  activeChatId,
  activeChat,
  servers,
  me,
  onSelectChat,
  onNewChat,
  onDeleteChat,
  onRenameChat,
  onTogglePin,
  onCopyChat,
  onMessageSent,
  onForked,
  onOpenSettings,
  settingsOpen,
  onCloseSettings,
  onAddServer,
  onUpdateServer,
  onDeleteServer,
  onMeUpdated,
  onAccountDeleted,
}) {
  const [menuId, setMenuId] = useState(null);

  if (activeChat) {
    return (
      <div className="mobile-shell">
        <ChatView
          chat={activeChat}
          servers={servers}
          onMessageSent={onMessageSent}
          onForked={onForked}
          onOpenSettings={onOpenSettings}
          mobile
          onBack={() => onSelectChat(null)}
        />

        {settingsOpen && (
          <SettingsModal
            servers={servers}
            me={me}
            onClose={onCloseSettings}
            onAdd={onAddServer}
            onUpdate={onUpdateServer}
            onDelete={onDeleteServer}
            onMeUpdated={onMeUpdated}
            onAccountDeleted={onAccountDeleted}
          />
        )}
      </div>
    );
  }

  return (
    <div className="mobile-shell">
      <header className="mobile-home-header">
        <div>
          <div className="mobile-brand">Max</div>
          <div className="mobile-subtitle">Conversations</div>
        </div>

        <div className="mobile-home-actions">
          <button
            type="button"
            className="mobile-header-button"
            onClick={onNewChat}
            aria-label="New conversation"
          >
            +
          </button>

          <button
            type="button"
            className="mobile-header-button"
            onClick={onOpenSettings}
            aria-label="Settings"
          >
            ⚙
          </button>
        </div>
      </header>

      <main className="mobile-conversation-list">
        {chats.length === 0 ? (
          <button
            type="button"
            className="mobile-empty-state"
            onClick={onNewChat}
          >
            <span className="mobile-empty-icon">＋</span>
            <strong>Start a conversation</strong>
            <span>Your chats will appear here.</span>
          </button>
        ) : (
          chats.map((chat) => {
            const title = titleForChat(chat);
            const preview = previewForChat(chat);
            const isMenuOpen = menuId === chat.id;

            return (
              <div className="mobile-conversation-row" key={chat.id}>
                <button
                  type="button"
                  className="mobile-conversation-main"
                  onClick={() => onSelectChat(chat.id)}
                >
                  <span className="mobile-avatar" aria-hidden="true">
                    M
                  </span>

                  <span className="mobile-conversation-copy">
                    <span className="mobile-conversation-title">
                      {chat.pinned ? "📌 " : ""}
                      {title}
                    </span>

                    <span className="mobile-conversation-preview">
                      {preview || "No messages yet"}
                    </span>
                  </span>
                </button>

                <button
                  type="button"
                  className="mobile-more-button"
                  onClick={() =>
                    setMenuId(isMenuOpen ? null : chat.id)
                  }
                  aria-label={`Actions for ${title}`}
                >
                  ⋮
                </button>

                {isMenuOpen && (
                  <div className="mobile-chat-menu">
                    <button
                      type="button"
                      onClick={() => {
                        const value = window.prompt(
                          "Rename conversation",
                          title
                        );

                        if (value?.trim()) {
                          onRenameChat(chat.id, value.trim());
                        }

                        setMenuId(null);
                      }}
                    >
                      Rename
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        onTogglePin(chat.id);
                        setMenuId(null);
                      }}
                    >
                      {chat.pinned ? "Unpin" : "Pin"}
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        onCopyChat(chat.id);
                        setMenuId(null);
                      }}
                    >
                      Copy
                    </button>

                    <button
                      type="button"
                      onClick={() => {
                        onDeleteChat(chat.id);
                        setMenuId(null);
                      }}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
            );
          })
        )}
      </main>

      {settingsOpen && (
        <SettingsModal
          servers={servers}
          me={me}
          onClose={onCloseSettings}
          onAdd={onAddServer}
          onUpdate={onUpdateServer}
          onDelete={onDeleteServer}
          onMeUpdated={onMeUpdated}
          onAccountDeleted={onAccountDeleted}
        />
      )}
    </div>
  );
}
