/** Confirmation only; callers own the transactional send/fork operation. */
export default function ContextSettingsDialog({ reasons, busy = false, onContinue, onFork, onCancel }) {
  const names = { model: "model", system_prompt: "system prompt", tools: "tool availability" };
  const parts = (reasons || []).map((reason) => names[reason] || reason);
  const differences = parts.length < 2 ? parts.join("") :
    `${parts.slice(0, -1).join(", ")} or ${parts[parts.length - 1]}`;
  return (
    <div role="presentation" className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4">
      <div role="dialog" aria-modal="true" aria-labelledby="context-settings-title"
           className="w-full max-w-lg rounded-xl border border-neutral-600 bg-neutral-900 p-5 text-neutral-100 shadow-xl">
        <h2 id="context-settings-title" className="text-lg font-semibold">Different conversation settings</h2>
        <p className="mt-3 text-sm text-neutral-300">
          This conversation uses different {differences || "settings"}. Continuing will refill the full conversation context. You can fork instead.
        </p>
        <div className="mt-5 flex flex-col gap-3">
          <button type="button" disabled={busy} onClick={onContinue}
                  className="rounded-lg border border-neutral-500 p-3 text-left hover:bg-neutral-800 disabled:opacity-50">
            <strong className="block">Continue with current settings</strong>
            <span className="block text-sm text-neutral-400">Keep this conversation and rebuild its context using the current model, prompt and tools.</span>
          </button>
          <button type="button" disabled={busy} onClick={onFork}
                  className="rounded-lg border border-neutral-500 p-3 text-left hover:bg-neutral-800 disabled:opacity-50">
            <strong className="block">Fork with current settings</strong>
            <span className="block text-sm text-neutral-400">Keep the original intact. Rebuilding the fork’s context may take time.</span>
          </button>
        </div>
        <button type="button" disabled={busy} onClick={onCancel}
                className="mt-4 text-sm text-neutral-300 underline disabled:opacity-50">Cancel</button>
      </div>
    </div>
  );
}
