# Max

Max is an independent downstream fork of [Calivi](https://github.com/orkun-soylu/calivi).

Max keeps useful parts of Calivi while developing its own UI, retrieval, tooling, context management, and local-AI workflow.

> **Current status:** Max has been rebased onto Calivi v0.6.5. The current Calivi UI is now the foundation for Max's UI development. The previous Max-specific mobile UI and OpenDyslexic integration were deliberately left behind during the rebase and will be rebuilt on this newer foundation.

## Current stack

* Local AI chat backend
* Docker Compose deployment
* Calivi UI foundation
* Local web search and page retrieval
* Dedicated search service using Camoufox
* DuckDuckGo search with Brave fallback
* Mozilla Readability for page extraction
* Built-in `web_search` and `web_fetch` tools
* Configurable search timeout
* Context usage and conversation compaction inherited from current Calivi
* `max.sh` for managing the local stack and search service

## Requirements

* Linux
* Docker and Docker Compose
* Python 3
* A local OpenAI-compatible model endpoint
* Camoufox for the local search service

Max is designed around a local/self-hosted setup. External model providers are not required.

## Installation

Clone the repository and enter the project directory:

```bash
git clone https://github.com/davidrutland/Max.git
cd Max
```

Copy the example environment file:

```bash
cp .env.example .env
```

Install the search-service environment:

```bash
./search_service/setup.sh
```

Start Max:

```bash
./max.sh start
```

The frontend is available on the configured Calivi port.

## Environment

The main configurable values are documented in `.env.example`.

Important settings include:

```text
CALIVI_PORT=8090
COOKIE_SECURE=false
CALIVI_SECRET_KEY=
CALIVI_SECRET_KEY_OLD=
OLLAMA_CHAT_TIMEOUT=300
SEARCH_TIMEOUT=15
```

`SEARCH_TIMEOUT` controls the timeout used by the backend when communicating with the local search infrastructure.

## Search

Max's search path uses the local `calivi-search` integration and the host-side `search_service`.

`search_service` provides the actual search-engine access:

* DuckDuckGo is the primary search engine.
* Brave is used as a fallback.
* Search results are normalised and deduplicated.
* Retrieved pages can be extracted using Mozilla Readability.

The built-in `web_search` tool uses the configured `calivi-search` engine.

`web_fetch` provides direct page retrieval through the local search service and is intended for fetching and extracting the contents of a specific URL.

The search service runs separately from the Docker containers on port `8787` and is managed by `max.sh`.

## Managing Max

The `max.sh` wrapper manages both the Docker Compose stack and the local search service.

```bash
./max.sh start
./max.sh stop
./max.sh restart
./max.sh status
```

The search service is only stopped by the wrapper when it is the process that the wrapper started.

Runtime logs are stored under:

```text
search_service/logs/
```

## Context and compaction

Max currently uses the context handling and conversation compaction functionality absorbed from the current Calivi codebase during the rebase onto v0.6.5.

The UI exposes context usage and the available compaction controls. Compaction is part of the current Max implementation rather than a future roadmap item.

Further context-management work may build on this foundation, particularly around preserving useful information from long conversations.

## Development

The backend is a Python application and the frontend is a Vite/React application.

Backend code:

```text
backend/
```

Frontend code:

```text
frontend/
```

Search service:

```text
search_service/
```

SearXNG configuration retained in the repository is supporting infrastructure for the Calivi stack and is not the logical Max search interface.

Build the frontend/backend containers with:

```bash
docker-compose build
```

Start the stack with:

```bash
./max.sh start
```

## Upstream relationship

Max is an independent downstream project.

Calivi is treated as an upstream source of useful fixes, features, and ideas. Upstream changes may be selectively incorporated when they fit Max's architecture and goals.

Max does not attempt to remain a patch-for-patch copy of Calivi.

See [`UPSTREAM.md`](UPSTREAM.md) for the fork point and porting policy.

## Roadmap

### UI

* Continue rebuilding Max's UI on the current Calivi foundation
* Restore and improve Max-specific UI features where useful
* Continue improving desktop and mobile usability

### Context and conversation

* Build further on the current compaction system
* Improve handling of very long conversations
* Preserve important decisions, facts, and unresolved questions during future context-management work
* Explore persistent memory where appropriate

### Retrieval

* Continue improving search quality and source selection
* Improve page extraction and retrieval reliability
* Reduce unnecessary search/tool calls

### Tools

* Expand useful local tools
* Improve tool selection and execution
* Keep tool interfaces simple and model-friendly

### Local AI

* Continue optimising Max for self-hosted local models
* Keep external dependencies and unnecessary cloud services to a minimum
