import { useEffect, useRef, useState } from "react";
import ServerModelPicker from "./ServerModelPicker.jsx";
import ContextSettingsDialog from "./ContextSettingsDialog.jsx";
import MessageList from "./chat/MessageList.jsx";
import ToolOutputModal from "./chat/ToolOutputModal.jsx";
import ContextBar from "./chat/ContextBar.jsx";
import Composer from "./chat/Composer.jsx";
import { CompactIcon, SaveIcon, SettingsIcon } from "./icons.jsx";
import { useChatStream } from "../hooks/useChatStream.js";
import { useServerModel } from "../hooks/useServerModel.js";
import useModelReadiness from "../hooks/useModelReadiness.js";
import { fileToScaledDataUrl } from "../lib/images.js";
import { ASK_EVERY_TOOL_KEY, USE_TOOLS_KEY, loadAskEveryTool, loadUseTools } from "../lib/modelPrefs.js";
import { api } from "../api.js";
import { useT } from "../i18n.js";

/** Orchestrates the chat screen: combines the selected target (useServerModel), stream state
 * (useChatStream) and attachment/edit state; the rendering is done by child components. */
export default function ChatView({ chat, servers, hostTools, onMessageSent, onForked, onOpenSettings, onBack, searchTarget, forkDraft, onForkDraftConsumed }) {
  const t = useT();
  const { serverId, model, setTarget, upServers, selectedServer } = useServerModel(servers);
  const [contextStatus, setContextStatus] = useState(null);
  const [readinessRefresh, setReadinessRefresh] = useState(0);
  const routerTarget = contextStatus?.enabled === true &&
    contextStatus.owner_server_id === serverId && contextStatus.owner_model === model;
  const modelReadiness = useModelReadiness(model, routerTarget, readinessRefresh);
  const modelReady = !routerTarget || modelReadiness.ready;
  const [switchingModel, setSwitchingModel] = useState(false);

  async function handleModelSelection(target) {
    if (switchingModel || stream.sending) return;

    if (target.serverId === serverId && target.model === model) return;

    if (persistent && model && target.model !== model) {
      if (!window.confirm(
        `Switch from ${model} to ${target.model}? The current context will be saved.`
      )) return;
    }

    setSwitchingModel(true);
    try {
      if (persistent && contextStatus?.owner_server_id === target.serverId && contextStatus?.owner_model === target.model) await api.selectRouterModel(target.model);
      setTarget(target);
    } catch (error) {
      window.alert(`Model selection failed: ${error.message}`);
    } finally {
      setSwitchingModel(false);
    }
  }

  async function loadSelectedModel() {
    if (!routerTarget || !model || switchingModel || stream.sending) return;
    setSwitchingModel(true);
    try {
      await api.selectRouterModel(model);
      setReadinessRefresh(value => value + 1);
    } catch (error) {
      window.alert(`Model loading failed: ${error.message}`);
    } finally {
      setSwitchingModel(false);
    }
  }

  const stream = useChatStream();
  const [inspecting, setInspecting] = useState(null); // tool output being read
  const [compacting, setCompacting] = useState(null); // {chars} while a summary is being written
  const compactAbortRef = useRef(null);

  const [contextBusy, setContextBusy] = useState(false);
  const [savingContext, setSavingContext] = useState(false);
  const [settingsConflict, setSettingsConflict] = useState(null);
  const contextBusyRef = useRef(false);
  const contextChatIdRef = useRef(chat?.id);
  contextChatIdRef.current = chat?.id;

  const currentContextStatus =
    contextStatus?.chatId === chat?.id ? contextStatus : null;
  const persistent = currentContextStatus?.enabled === true;
  const contextActive =
    currentContextStatus !== null &&
    (!persistent || currentContextStatus.active_chat_id === chat?.id);

  async function refreshContextStatus(chatId) {
    const status = await api.getContextStatus(chatId);
    if (contextChatIdRef.current === chatId) {
      setContextStatus({ ...status, chatId });
    }
    return status;
  }

  useEffect(() => {
    let cancelled = false;
    let retryTimer = null;
    setContextStatus(null);
    const chatId = chat.id;

    async function loadStatus() {
      try {
        const status = await api.getContextStatus(chatId);
        if (!cancelled && contextChatIdRef.current === chatId) {
          setContextStatus({ ...status, chatId });
        }
      } catch (error) {
        if (!cancelled) {
          retryTimer = setTimeout(loadStatus, 2000);
        }
      }
    }

    loadStatus();
    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
    };
  }, [chat?.id]);

  useEffect(() => {
    if (!routerTarget || !chat?.id || stream.sending) return;
    refreshContextStatus(chat.id).catch(() => {});
  }, [chat?.id, chat?.updated_at, routerTarget, stream.sending]);

  // Refresh the tick after background/automatic checkpoint writes and other tabs.
  useEffect(() => {
    if (!routerTarget || !chat?.id || stream.sending || savingContext) return;
    const id = chat.id;
    const timer = setInterval(() => {
      refreshContextStatus(id).catch(() => {});
    }, 5000);
    return () => clearInterval(timer);
  }, [chat?.id, routerTarget, stream.sending, savingContext]);

  const [input, setInput] = useState("");
  const [images, setImages] = useState([]); // scaled vision images
  const [imageUploadIds, setImageUploadIds] = useState([]); // original bytes, aligned with images
  const [attachments, setAttachments] = useState([]); // attached documents {name, text}
  const [pending, setPending] = useState({ user: null, images: [], attachments: [] });
  const [lightbox, setLightbox] = useState(null); // image to display full size (data-URI)
  const [useTools, setUseTools] = useState(loadUseTools);
  const [askEveryToolPref, setAskEveryTool] = useState(loadAskEveryTool);
  // Only in effect where the toggle is visible — a preference left over in this browser must
  // not put cards on a user who cannot see the switch that caused them.
  const askEveryTool = !!hostTools && askEveryToolPref;

  const [editingId, setEditingId] = useState(null);
  const [editingRole, setEditingRole] = useState(null);
  const [editContent, setEditContent] = useState("");
  const [editTarget, setEditTarget] = useState({ serverId: null, model: "" });

  const supportsVision = !!selectedServer?.vision_models?.includes(model);
  const canSend = (!!input.trim() || !!images.length || !!attachments.length) && !!serverId && !!model && modelReady && !switchingModel;

  useEffect(() => {
    localStorage.setItem(USE_TOOLS_KEY, useTools ? "1" : "0");
  }, [useTools]);

  useEffect(() => {
    localStorage.setItem(ASK_EVERY_TOOL_KEY, askEveryToolPref ? "1" : "0");
  }, [askEveryToolPref]);

  // Clear attached images if the model does not support vision (they cannot be sent).
  useEffect(() => {
    if (!supportsVision) setImages([]);
  }, [supportsVision]);

  // Background turns (#85). Switching to another chat stops *following* a reply — it keeps
  // running on the server — and opening a chat whose reply is still running re-attaches to it:
  // after a reload, on another device, or on coming back. The replay brings a pending approval
  // card back with it. `beforeClear` reloads the chat before the stream state clears, so the
  // reloaded detail (active_turn now false) is what the next render sees — no second attach.
  useEffect(() => {
    if (stream.sending && stream.followedChatId() !== chat?.id) stream.detach();
  }, [chat?.id]);

  useEffect(() => {
    if (!chat?.active_turn || stream.sending) return;
    const id = chat.id;
    stream.run(({ signal, onPiece }) => api.followTurn(id, { signal }, onPiece), {
      chatId: id,
      agent: chat.mode === "agent",
      beforeClear: () => onMessageSent(),
    });
  }, [chat?.id, chat?.active_turn, stream.sending]);

  // While the lightbox is open Esc closes it — and does NOT stop the stream.
  // useChatStream also binds Escape on window (to cancel the stream). Pressing Esc with the
  // lightbox open used to cancel the in-flight answer; the user lost the generation while
  // only meaning to close the overlay. capture:true runs this listener BEFORE the other one
  // (deterministic, independent of registration order), and stopPropagation keeps it from firing.
  useEffect(() => {
    if (!lightbox) return;
    function onKey(e) {
      if (e.key !== "Escape") return;
      e.stopPropagation();
      setLightbox(null);
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [lightbox]);

  async function addFiles(files) {
    // Images → vision (only on models that support it); everything else → document text extraction (all models).
    // On a non-vision model an image is not dropped SILENTLY: the user must see why it was not attached.
    if (!supportsVision && files.some((f) => f.type.startsWith("image/"))) {
      stream.flashError(t("chat.visionUnsupported"));
    }
    const imgs = supportsVision ? files.filter((f) => f.type.startsWith("image/")) : [];
    const docs = files.filter((f) => !f.type.startsWith("image/"));
    for (const f of imgs) {
      let uploaded;
      try {
        // The original is stored separately from the scaled vision representation.
        uploaded = await api.uploadBinary(f);
        const url = await fileToScaledDataUrl(f);
        setImages((prev) => [...prev, url]);
        setImageUploadIds((prev) => [...prev, uploaded.id]);
        setAttachments((prev) => [...prev, { name: uploaded.name, upload_id: uploaded.id }]);
      } catch (e) {
        if (uploaded?.id) api.deleteUnusedUpload(uploaded.id).catch(() => {});
        stream.flashError(`${f.name}: ${e.message}`);
      }
    }
    for (const f of docs) {
      try {
        // Preserve arbitrary binaries; retain text extraction for supported document types.
        const isDocument = /\.(pdf|docx|txt|md|markdown|csv|json|yml|yaml|log|py|js|jsx|ts|tsx|sh|html|css|xml|sql|toml|ini)$/i.test(f.name) || f.type.startsWith("text/");
        if (isDocument) {
          const { name, text } = await api.extractFile(f);
          setAttachments((prev) => [...prev, { name, text }]);
        } else {
          const uploaded = await api.uploadBinary(f);
          setAttachments((prev) => [...prev, { name: uploaded.name, upload_id: uploaded.id }]);
        }
      } catch (e) {
        stream.flashError(`${f.name}: ${e.message}`);
      }
    }
  }

  function handlePaste(e) {
    const files = Array.from(e.clipboardData?.items || [])
      .filter((it) => it.type.startsWith("image/"))
      .map((it) => it.getAsFile())
      .filter(Boolean);
    if (!files.length) return; // plain-text paste — leave the default behaviour alone
    e.preventDefault();
    // The vision check lives HERE, not in an early return: pasting on a non-vision model used
    // to die without a trace ("images don't paste from the clipboard" report). addFiles warns.
    addFiles(files);
  }

  async function handleSend(override = null) {
    if ((!override && !canSend) || stream.sending || savingContext || contextBusyRef.current) return;
    const content = override ? override.content : input.trim();
    const imgs = override ? override.images : images;
    const atts = override ? override.attachments : attachments;
    const chosenServer = override ? override.serverId : serverId;
    const chosenModel = override ? override.model : model;
    const chosenTools = override ? override.useTools : useTools;
    const chosenAsk = override ? override.askEveryTool : askEveryTool;
    const continueOriginal = false;
    const confirmedChange = !!override?.confirmConfigurationChange;

    if (currentContextStatus === null || contextBusyRef.current) return;

    // Check before touching Buun or clearing the draft. The server also checks
    // again before committing the message, so this UI is advisory, not security.
    const proposed = { content, images: imgs, attachments: atts, serverId: chosenServer, model: chosenModel, useTools: chosenTools, askEveryTool: chosenAsk, continueOriginal };
    let eligibleForPersistence = persistent;
    if (persistent && !confirmedChange) {
      contextBusyRef.current = true;
      setContextBusy(true);
      try {
        const decision = await api.checkContextCompatibility(chat.id, proposed);
        eligibleForPersistence = decision.enabled;
        if (decision.requires_confirmation) {
          setSettingsConflict({ reasons: decision.reasons, chatId: chat.id, proposed });
          return;
        }
      } catch (error) {
        stream.flashError(error.message);
        return;
      } finally {
        contextBusyRef.current = false;
        setContextBusy(false);
      }
    }

    if (eligibleForPersistence && !confirmedChange && (!contextActive || !currentContextStatus.initialized)) {
      contextBusyRef.current = true;
      setContextBusy(true);
      try {
        const payload = {
          content, images: imgs, attachments: atts,
          serverId: chosenServer, model: chosenModel, useTools: chosenTools, askEveryTool: chosenAsk, continueOriginal,
        };
        const chatId = chat.id;
        if (!currentContextStatus.initialized) {
          await api.initializeChatContext(chatId, payload);
        }
        await api.activateChatContext(chatId);
        const status = await refreshContextStatus(chatId);
        if (contextChatIdRef.current !== chat.id ||
            status.active_chat_id !== chat.id) {
          throw new Error("Persistent context activation was not confirmed");
        }
      } catch (error) {
        stream.flashError(error.message);
        return;
      } finally {
        contextBusyRef.current = false;
        setContextBusy(false);
      }
    }

    setInput("");
    setImages([]);
    setImageUploadIds([]);
    setAttachments([]);
    setPending({ user: content, images: imgs, attachments: atts });

    await stream.run(
      ({ signal, onPiece }) =>
        api.sendMessage(
          chat.id,
          { content, images: imgs, attachments: atts, serverId: chosenServer, model: chosenModel, useTools: chosenTools, askEveryTool: chosenAsk, continueOriginal, confirmConfigurationChange: confirmedChange, signal },
          onPiece
        ),
      {
        chatId: chat.id,
        agent: chat.mode === "agent",
        // Clear the streaming bubble only AFTER the new message lands in the list (no empty gap).
        beforeClear: async () => {
          await onMessageSent();
          setPending({ user: null, images: [], attachments: [] });
        },
      }
    );
  }

  const forkStartedRef = useRef(null);
  useEffect(() => {
    if (!forkDraft || forkStartedRef.current === chat.id) return;
    // A fork navigates to a new chat, but useServerModel retains its previous
    // selection. Set the fork's requested target before trying to send.
    if (serverId !== forkDraft.serverId || model !== forkDraft.model) {
      setTarget({ serverId: forkDraft.serverId, model: forkDraft.model });
      return;
    }
    // Wait for the new chat's status and model readiness. The previous code
    // consumed the draft while the new model could still be loading.
    if (currentContextStatus === null || !modelReady || contextBusyRef.current) return;
    forkStartedRef.current = chat.id;
    setInput(forkDraft.content);
    setImages(forkDraft.images || []);
    setImageUploadIds((forkDraft.images || []).map(() => null));
    setAttachments(forkDraft.attachments || []);
    onForkDraftConsumed();
    handleSend(forkDraft).catch((error) => stream.flashError(error.message));
  }, [forkDraft, currentContextStatus, chat.id, serverId, model, modelReady]);

  async function resolveSettingsConflict(choice) {
    const conflict = settingsConflict;
    if (!conflict || contextBusyRef.current) return;
    if (choice === "cancel") { setSettingsConflict(null); return; }
    if (choice === "continue") {
      setSettingsConflict(null);
      await handleSend({ ...conflict.proposed, confirmConfigurationChange: true });
      return;
    }
    contextBusyRef.current = true;
    setContextBusy(true);
    try {
      const result = await api.forkConversation(conflict.chatId, conflict.proposed);
      setSettingsConflict(null);
      // Keep the draft intact: navigating to the fork must not send to the parent.
      onForked(result.chat_id, conflict.proposed);
    } catch (error) {
      stream.flashError(error.message);
    } finally {
      contextBusyRef.current = false;
      setContextBusy(false);
    }
  }

  function startEdit(m) {
    setEditingId(m.id);
    setEditingRole(m.role);
    setEditContent(m.content);
    setEditTarget({ serverId, model });
  }

  function cancelEdit() {
    setEditingId(null);
    setEditingRole(null);
    setEditContent("");
  }

  // Answers a pending tool approval. The stream is still open and resumes on its own once the
  // backend records the decision, so there is nothing to do with the response here.
  async function handleApprovalDecision(approvalId, approved) {
    if (!chat) return;
    await api.respondToApproval(chat.id, approvalId, approved);
  }

  async function handleDeleteMessage(id) {
    if (stream.sending) return;
    if (editingId === id) cancelEdit();
    await api.deleteMessage(chat.id, id);
    await onMessageSent();
  }

  async function handleUpdate() {
    if (!editContent.trim() || stream.sending) return;
    const mid = editingId;
    const content = editContent.trim();
    const hasLaterMessages = chat.messages?.some(m => m.id > mid);
    if (hasLaterMessages && !window.confirm(
      "Editing this message will remove every later message in this conversation. Continue?"
    )) return;
    if (editingRole === "assistant") {
      try {
        await api.editAssistantMessage(chat.id, mid, content, editTarget.serverId, editTarget.model, useTools);
        cancelEdit();
        await onMessageSent();
      } catch (error) {
        stream.flashError(error.message);
      }
      return;
    }
    cancelEdit();
    await stream.run(
      ({ signal, onPiece }) =>
        api.editMessage(chat.id, mid, { content, ...editTarget, useTools, askEveryTool, signal }, onPiece),
      { chatId: chat.id, agent: chat.mode === "agent", beforeClear: () => onMessageSent() }
    );
  }

  async function handleFork() {
    if (!editContent.trim() || stream.sending) return;
    const mid = editingId;
    const content = editContent.trim();
    await stream.run(
      ({ signal, onPiece }) =>
        api.forkChat(
          chat.id,
          { messageId: mid, content, ...editTarget, useTools, askEveryTool, signal },
          (newId) => {
            // Keep the editor open if the fork request is rejected.
            cancelEdit();
            // Follow the new chat *before* switching to it, so the switch does not detach.
            stream.setChatId(newId);
            onForked(newId);
          },
          onPiece
        ),
      { agent: chat.mode === "agent", afterClear: () => onMessageSent() }
    );
  }

  async function handleSaveContext() {
    if (!routerTarget || !persistent || !currentContextStatus?.initialized ||
        !contextActive || savingContext || compacting || stream.sending ||
        chat.active_turn || contextBusy || switchingModel) return;
    setSavingContext(true);
    try {
      await api.saveChatContext(chat.id);
      await refreshContextStatus(chat.id);
    } catch (error) {
      stream.flashError(error.message);
    } finally {
      setSavingContext(false);
    }
  }

  // Compaction (#62): always user-triggered. Uses the model picked in the header.
  async function handleCompact() {
    if (compacting || savingContext || stream.sending || !serverId || !model) return;
    const ctrl = new AbortController();
    compactAbortRef.current = ctrl;
    setCompacting({ chars: 0 });
    let failed = null;
    try {
      await api.compactChat(chat.id, { serverId, model, signal: ctrl.signal }, (piece) => {
        if (piece.type === "content") setCompacting((c) => ({ chars: (c?.chars || 0) + piece.text.length }));
        else if (piece.type === "error") failed = piece.message;
      });
    } catch (e) {
      if (e.name !== "AbortError") failed = e.message;
    } finally {
      compactAbortRef.current = null;
      setCompacting(null);
    }
    if (failed) stream.flashError(failed);
    await onMessageSent();
  }

  // Agent mode (#91) keeps each reply's tool steps and replays them. Offered where the model can
  // operate the host; a chat switched back to plain chat keeps its steps but stops replaying them.
  async function toggleAgentMode() {
    await api.updateChat(chat.id, { mode: chat.mode === "agent" ? "chat" : "agent" });
    await onMessageSent();
  }

  async function handleSetContextMode(mode) {
    await api.updateChat(chat.id, { context_mode: mode });
    await onMessageSent();
  }

  function viewSummary() {
    setInspecting({
      name: t("compact.summaryTitle"),
      detail: chat.summary,
      label: t("compact.summaryLabel"),
      hint: t("compact.summaryHint"),
    });
  }

  const edit = {
    editingId,
    content: editContent,
    setContent: setEditContent,
    target: editTarget,
    setTarget: setEditTarget,
    cancel: cancelEdit,
    fork: handleFork,
    update: handleUpdate,
  };

  return (
    <div className="flex-1 min-w-0 flex flex-col h-dvh">
      <div className="flex items-center gap-2 md:gap-3 px-3 py-3 md:px-5 md:py-4">
        {/* Phone layout only (#61): back to the chat list. */}
        {onBack && (
          <button
            onClick={onBack}
            title={t("chat.back")}
            className="shrink-0 w-9 h-9 -ml-1 rounded-full hover:bg-neutral-800 text-2xl leading-none text-neutral-300"
          >
            ‹
          </button>
        )}
        <div className="flex items-center gap-2 md:gap-3 min-w-0 flex-1 md:flex-none">
          <ServerModelPicker servers={upServers} value={{ serverId, model }} onChange={handleModelSelection} />
          {model && routerTarget && (
            <span
              role="status"
              aria-live="polite"
              title={modelReadiness.error || undefined}
              className="text-xs opacity-70 whitespace-nowrap"
            >
              {({
                checking: "Checking…",
                loading: "Loading…",
                loaded: "Ready",
                unloaded: "Unloaded",
                failed: "Failed",
                unavailable: "Unavailable",
              })[modelReadiness.status] || modelReadiness.status}
            </span>
          )}
          {model && routerTarget && modelReadiness.status === "unloaded" && (
            <button type="button" onClick={loadSelectedModel}
              disabled={switchingModel || stream.sending}
              className="rounded border border-neutral-500 px-2.5 py-1 text-xs text-neutral-200 hover:bg-neutral-700 disabled:opacity-50">
              {switchingModel ? "Loading…" : "Load model"}
            </button>
          )}
        </div>
        {hostTools && (
          <button
            onClick={toggleAgentMode}
            disabled={stream.sending}
            aria-pressed={chat.mode === "agent"}
            title={t(chat.mode === "agent" ? "mode.agentTitle" : "mode.chatTitle")}
            className={`ml-auto shrink-0 rounded-full px-2.5 py-1 text-xs disabled:opacity-40 ${
              chat.mode === "agent" ? "bg-accent text-white" : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
            }`}
          >
            {t(chat.mode === "agent" ? "mode.agent" : "mode.chat")}
          </button>
        )}
        {chat.compactable && (
          <button
            onClick={handleCompact}
            disabled={!!compacting || savingContext || stream.sending}
            className={`${hostTools ? "" : "ml-auto "}shrink-0 text-neutral-300 opacity-70 hover:opacity-100 disabled:opacity-30`}
            title={t("compact.buttonTitle")}
          >
            <CompactIcon className="w-5 h-5" />
          </button>
        )}
        {routerTarget && persistent && currentContextStatus?.initialized && (
          <button
            type="button"
            onClick={handleSaveContext}
            disabled={savingContext || !!compacting || stream.sending || chat.active_turn ||
              !contextActive || contextBusy || switchingModel}
            className={`${chat.compactable || hostTools ? "" : "ml-auto "}relative shrink-0 text-neutral-300 opacity-70 hover:opacity-100 disabled:opacity-30`}
            title={savingContext ? "Saving context…" : "Save context to SSD"}
            aria-label="Save context to SSD"
          >
            <SaveIcon className={`w-5 h-5 ${savingContext ? "animate-pulse" : ""}`} />
            {!savingContext && !stream.sending && !chat.active_turn &&
              !compacting && !contextBusy && currentContextStatus.checkpoint_current && (
              <svg className="absolute -right-1 -bottom-1 w-3 h-3 text-green-400"
                viewBox="0 0 16 16" fill="none" stroke="currentColor"
                strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="m3 8 3 3 7-7" />
              </svg>
            )}
          </button>
        )}
        <button
          onClick={onOpenSettings}
          className={`${chat.compactable || hostTools || (routerTarget && persistent && currentContextStatus?.initialized) ? "" : "ml-auto "}shrink-0 text-neutral-300 opacity-70 hover:opacity-100`}
          title={t("common.settings")}
        >
          <SettingsIcon className="w-5 h-5" />
        </button>
      </div>

      <ContextBar
        chat={chat}
        compacting={compacting}
        onCompact={handleCompact}
        onStopCompact={() => compactAbortRef.current?.abort()}
        onSetMode={handleSetContextMode}
        onViewSummary={viewSummary}
      />

      <MessageList
        chat={chat}
        searchTarget={searchTarget}
        edit={edit}
        upServers={upServers}
        stream={stream}
        pending={pending}
        onImageClick={setLightbox}
        onStartEdit={startEdit}
        onDeleteMessage={handleDeleteMessage}
        onDecide={handleApprovalDecision}
        onInspect={setInspecting}
      />

      <Composer
        input={input}
        onInputChange={setInput}
        onSend={handleSend}
        onStop={stream.stop}
        sending={stream.sending}
        canSend={canSend && currentContextStatus !== null && !contextBusy && !savingContext && !compacting}
        images={images}
        onRemoveImage={(i) => {
          const id = imageUploadIds[i];
          setImages((prev) => prev.filter((_, j) => j !== i));
          setImageUploadIds((prev) => prev.filter((_, j) => j !== i));
          if (id) {
            setAttachments((prev) => prev.filter((a) => a.upload_id !== id));
            api.deleteUnusedUpload(id).catch((e) => stream.flashError(e.message));
          }
        }}
        attachments={attachments}
        onRemoveAttachment={(i) => {
          const removed = attachments[i];
          setAttachments((prev) => prev.filter((_, j) => j !== i));
          if (removed?.upload_id) {
            const imageIndex = imageUploadIds.indexOf(removed.upload_id);
            if (imageIndex !== -1) {
              setImages((prev) => prev.filter((_, j) => j !== imageIndex));
              setImageUploadIds((prev) => prev.filter((_, j) => j !== imageIndex));
            }
            api.deleteUnusedUpload(removed.upload_id).catch((e) => stream.flashError(e.message));
          }
        }}
        onFiles={addFiles}
        onPaste={handlePaste}
        useTools={useTools}
        onToggleUseTools={() => setUseTools((v) => !v)}
        hostTools={!!hostTools}
        askEveryTool={askEveryTool}
        onToggleAskEveryTool={() => setAskEveryTool((v) => !v)}
      />

      {settingsConflict?.chatId === chat.id && (
        <ContextSettingsDialog
          reasons={settingsConflict.reasons}
          busy={contextBusy}
          onContinue={() => resolveSettingsConflict("continue")}
          onFork={() => resolveSettingsConflict("fork")}
          onCancel={() => resolveSettingsConflict("cancel")}
        />
      )}
      <ToolOutputModal tool={inspecting} onClose={() => setInspecting(null)} />

      {lightbox && (
        <div
          onClick={() => setLightbox(null)}
          className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-6 cursor-zoom-out"
        >
          <img src={lightbox} alt="" className="max-h-full max-w-full rounded-lg" />
        </div>
      )}
    </div>
  );
}
