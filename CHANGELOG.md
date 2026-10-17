## Max

### 2026-10-17 — Conversation search

#### Added

- Authenticated, user-scoped search across stored conversation messages.
- Deterministic Boolean query parsing with `AND`, `OR`, `NOT`,
  implicit AND, quoted phrases, parentheses, `+`, `-`, `|`,
  and prefix wildcard matching.
- Live sidebar search with debounced requests, matching message excerpts,
  result counts, and independent scrolling.
- Exact-message navigation from search results, including repeated jumps
  within the same conversation.
- Temporary message-bubble highlighting and a divider separating search
  results from conversation groups.
- Paginated `/api/search/messages` endpoint.
- Search parser, API, frontend interaction, and navigation regression tests.

#### Behaviour

- Search is lexical and deterministic, without semantic or LLM matching.
- Search does not load or switch inference-model contexts.
- Closing search preserves the currently open conversation.
- Desktop and mobile search behaviour verified in the running interface.
- No database migration or FTS index is required by the initial implementation.

### 2026-10-16 — OpenHands integration and chat management

#### Added

- OpenHands agent-server as a default Compose service, with persistent workspace storage and resource limits.
- Five sandbox tools: `sandbox_exec`, `sandbox_edit`, `sandbox_write`, `sandbox_read`, and `sandbox_ls`. Sandbox operations intentionally do not require per-call approval.
- Archive and restore operations, including bulk archive/unarchive and a collapsed Archived accordion.
- Multi-chat selection, age-based conversation groups, and a separate Pinned group.
- Backend archive/migration regression tests and frontend chat-management/mobile-navigation tests.

#### Changed

- Improved desktop and mobile chat navigation, including mobile list/chat switching.
- Updated conversation-list controls, accordion styling, and selection behaviour.
- Documented the low-resource reference installation and external inference dependencies.
- Retained custom search with enhanced snippets and readable page fetching.

#### Deployment

- Reference hardware: 6 GB VRAM and 16 GB system RAM, running quantized models in the approximately 20B–80B range.
- Default reference model: Qwen3.6-35B-A3B APEX on Buun.
- Model weights and inference software are external to the Docker Compose stack.
- Sandbox execution is container-based, not network-isolated.
- Back up SQLite data and the persistent session/encryption key before upgrading.

### 2026-10-01 — Rebase onto Calivi v0.6.5

### Changed

* Rebased Max onto **Calivi v0.6.5**, retaining the current Calivi UI and conversation compaction system.
* Removed the previous Max-specific mobile UI and OpenDyslexic integration as part of the UI migration. These will be rebuilt on the newer Calivi UI foundation.
* Restored Max's intended web-search architecture: the backend queries the bundled SearXNG JSON API, which uses the custom `calivi-search` engine to reach Max's local `search_service`.
* Restored the `calivi-search` SearXNG engine configuration while leaving the upstream SearXNG engine definitions intact but disabled for Max's internal search facade.
* Made the search timeout configurable through `SEARCH_TIMEOUT`.

### Added

* `max.sh` for starting, stopping, restarting and checking the Max stack, including the host-side search service.
* `web_fetch` as a built-in tool for retrieving web pages through Max's local search service.
* `.env.example` documenting the main Max runtime configuration.
* `UPSTREAM.md` documenting Max's relationship with Calivi and the policy for selectively incorporating upstream changes.

### 2026-09-25 — Initial Max fork

### Added

* Max's local `search_service` for web search and page retrieval, using DuckDuckGo with Brave fallback. Page fetching uses Mozilla Readability to extract useful content and return compact Markdown instead of raw HTML.
* WhatsApp-style mobile web UI.
* Handy start / stop / status commands for the stack.
* When a model calls a tool by a name that does not exist but matches exactly one registered tool once the namespace is dropped (`scan_packages` for `mcp__cve__scan_packages`), the error returned to the model now names the real tool, so its next attempt can succeed. The tool is not run on the guess.
* A favicon, so the browser tab shows the Calivi mark instead of a blank page icon. It is the same mark the calivi.ai landing page uses.
* `OLLAMA_CHAT_TIMEOUT` is now configurable via environment variable (seconds, default `300`, unchanged). The old hard-coded value silently dropped very large prompts: it caps the silence between stream chunks, and prompt processing produces none, so a prompt big enough to prefill for over five minutes timed out before the model had said anything — with no hint that its size was the cause. Large-context setups can now raise it.

---

## Max fork point

Max was forked from Calivi on **2026-09-25** at commit `c6bf39424796d3c26e2124c9431bf11609a54117` (`Suggest the namespaced tool name when a model drops the prefix (#63)`).

Max is an independent downstream project. Calivi is treated as an upstream source of useful fixes and ideas; upstream changes may be selectively incorporated into Max when they are compatible with its architecture and goals.

---

## Calivi history

### [0.1.0] — 2026-07-22

The first tagged release. Everything below already worked before this tag; it marks a point
someone can install and stay on, instead of tracking `main`.

> **Heavy development.** Things break between commits, defaults change, and security holes get
> found and closed as the code moves. There is no stable channel yet and no versioned upgrade path —
> a migration is not guaranteed to leave an existing database untouched. Run it with backups.
> `0.1.0` is a starting line, not a stability promise.

### Added — chat and routing

* Self-hosted, multi-user chat for **Ollama** (native `/api/chat`) and any **OpenAI-compatible**
  server (`/v1/chat/completions`), through one interface.
* Server and model chosen from the top bar **per message**. Only servers that answered their last
  probe appear in the picker.
* Streaming replies, with reasoning models' thinking in a separate pane. Stop with the button or
  `Esc`; whatever streamed so far is kept.
* Retired cloud models are filtered out of the picker, so a model that died upstream cannot be
  selected into a broken chat.

### Added — control over a conversation

* Every reply stores the **model**, the **server** and the **tokens/sec** that produced it, so a
  chat reopened later still says what answered, where, and how fast.
* Delete a message to walk the conversation back.
* Edit a message and either regenerate from that point — optionally on a different model — or
  fork into a new chat, keeping the history intact.
* Copy a single answer, or the whole conversation, to the clipboard in one click.

### Added — tools, web search, MCP

* A tool layer behind one composer toggle. The model calls tools on its own initiative, and which
  tool ran stays visible in the conversation across reloads.
* Bundled **SearXNG** for web search — no external service, no API key.
* **MCP** servers over Streamable HTTP or HTTP+SSE, with presets for Context7, GitHub and Exa.
  Individual tools can be switched off without removing the server.
* Tool output is inspectable: every call opens its raw response, stored with the message.

### Added — safety

* **Approval before anything changes.** Read-only tools run on their own; anything that can change
  state is off until enabled, and then asks before every single run. Silence is a denial, never
  consent.
* **stdio MCP servers run in a separate sandboxed container** — its own `internal` network with no
  internet and no LAN, non-root, read-only filesystem, all capabilities dropped, no published
  port. Servers are pinned into the image rather than fetched at call time.
* **Secrets encrypted at rest.** Provider API keys and MCP tokens are encrypted in the database,
  so a copy of it is not a copy of your credentials.
* Brute-force protection on login, per-user chat isolation, and a super admin that cannot be
  demoted or deleted.

### Added — content

* Vision: images to vision-capable models, including paste-from-clipboard, with a full-screen
  viewer.
* Documents: PDF / docx / txt / code / csv / json extracted as **text** (not OCR) and handed to any
  model. Parsing runs in a killable subprocess with size and count caps.
* Markdown, tables, KaTeX, and code blocks with copy buttons.

### Added — interface and deployment

* Light/dark theme with a selectable accent colour; nine languages (TR, EN, DE, ES, IT, PT, RU, JA,
  ZH).
* `docker compose up -d --build` and nothing else. Data lives in SQLite.
* **About 700 MB on disk for the whole stack**, web search included — backend 230 MB, frontend
  95.8 MB, SearXNG 372 MB (measured on arm64).
