# Max

Max is an independent downstream fork of [Calivi](https://github.com/orkun-soylu/calivi), focused on building a reliable, easily deployable local AI stack with the tools and behaviour wanted here, without accumulating the problems or baggage that can come with larger projects.

Max keeps useful parts of Calivi where they make sense, while developing its own UI, retrieval, tooling, context management, and deployment approach.

For the broader Calivi architecture, features, and original documentation, see the [Calivi repository](https://github.com/orkun-soylu/calivi).

## Current stack

Max currently provides:

* A local AI chat application based on Calivi.
* Docker Compose deployment for the main application.
* A mobile-friendly, WhatsApp-style UI while retaining the desktop interface.
* OpenDyslexic font support.
* Local web search and page retrieval.
* A dedicated search/retrieval service using Camoufox and readability extraction.
* `web_search` and `web_fetch` tools.
* SearXNG as an internal JSON search facade.
* Configurable environment-based deployment settings.
* A single `max.sh` command for managing the Docker stack and local search service.

The intention is to keep the core deployment straightforward while allowing individual services to remain independently testable and replaceable.

## Installation

### Requirements

At minimum:

* Linux or another environment capable of running Docker Compose.
* Docker.
* Python 3.13 for the local search service.

Clone Max:

```bash
git clone https://github.com/davidrutland/Max.git
cd Max
```

### Configure the search service

The search service is included in the repository as a separate component.

Set it up with:

```bash
cd search_service
./setup.sh
cd ..
```

The service runs locally on port `8787` by default.

Check that it is working:

```bash
curl -sS http://127.0.0.1:8787/health
```

A healthy service should return a JSON response indicating that it is operational.

### Environment configuration

Copy `.env.example` to `.env` if you need to change the default deployment settings:

```bash
cp .env.example .env
```

The `.env` file is local configuration and is not committed to the repository.

## Running Max

The included `max.sh` script manages both the Docker application and the host-side search service.

Start:

```bash
./max.sh start
```

Check status:

```bash
./max.sh status
```

Stop:

```bash
./max.sh stop
```

Restart:

```bash
./max.sh restart
```

The script starts the search service when necessary and leaves an independently running, healthy search service alone.

Once started, open `http://127.0.0.1:8090/` in a browser. The default frontend port is `8090` and can be changed with `CALIVI_PORT` in `.env`.

The main Max services are managed through Docker Compose.

## Web search and retrieval

Max separates **search** from **page retrieval**.

### `web_search`

`web_search` queries the local search pipeline and returns **enhanced search-result snippets**.

The search service can perform search-engine queries, retrieve useful result information, and enhance the snippets returned to Max. This means the model should normally be able to answer from the search results without immediately fetching every individual result.

This is deliberate: fetching every result would add unnecessary latency, bandwidth, context usage, and opportunities for retrieval failures.

### `web_fetch`

`web_fetch` retrieves the readable content of a specific URL.

It should be used when the model needs:

* The actual text of an article or page.
* More detail than the search snippet provides.
* Source-specific verification.
* Information that is not adequately represented in the search results.

The intended pattern is therefore:

```text
web_search → enhanced snippets → answer when sufficient

web_search → identify relevant source → web_fetch → inspect full page
```

The search service is maintained separately from Max:

[github.com/davidrutland/search_service](https://github.com/davidrutland/search_service)

This keeps the browser, retrieval, and page-cleaning machinery independently testable and avoids making the Max backend responsible for the browser environment itself.

## Architecture

The current web-retrieval path is:

```text
Max backend
    │
    ├── web_search
    │       │
    │       ▼
    │   SearXNG
    │       │
    │       ▼
    │   search_service
    │       │
    │       └── search engines / browser retrieval / snippet enhancement
    │
    └── web_fetch
            │
            ▼
        search_service
            │
            └── readable page extraction
```

SearXNG is retained as an internal JSON-facing layer rather than being exposed as a separate user-facing search service.

## Development

Max is an independent downstream project. Changes are developed and tested here rather than being submitted as pull requests to the upstream Calivi project.

Useful checks before committing changes include:

```bash
git diff --check
```

For Python changes:

```bash
python -m compileall backend
```

And for Compose configuration:

```bash
docker-compose config
```

The project aims to keep changes small, understandable, and independently testable.

## Roadmap

The roadmap is deliberately practical rather than attempting to reproduce every feature of larger AI platforms.

### Context and conversation

* Better handling of large documents and attachments.
* Conversation summarisation and context compression.
* A structured `compress_conversation` representation containing:

  * events
  * decisions
  * key facts
  * unresolved questions
* Persistent memory and structured JSON state.
* Better preservation of useful context across context-window pressure and restarts.

### Retrieval

* More robust search-result handling.
* Search caching and deduplication.
* Better retrieval error reporting.
* An offline searchable document/index store.
* Clearer separation between retrieved evidence, metadata, and model context.
* Better handling of large source documents and uploaded files.

### Tools and sandboxing

* A proper sandbox, probably based on OpenHands.
* Python and shell execution within explicit security boundaries.
* Better tool error semantics so failures are clearly distinguishable from successful results.
* Continued expansion of useful local tools without unnecessarily expanding the core application.

### UI

* Further improvements to the mobile interface.
* Additional desktop UI improvements.
* Better presentation of tool activity, retrieved sources, and long-running operations.

### External information

* A real-time date/time tool rather than injecting changing timestamps into the stable system prompt.
* Current web information without unnecessarily invalidating the model's cached prompt prefix.
* RSS integration, including support for self-hosted services such as FreshRSS.

## Philosophy

Max is intended to remain relatively small and understandable.

The goal is not to build an everything-platform. The goal is to have a local AI assistant that can reason, use useful tools, retrieve evidence, work with local data, and remain practical to deploy and maintain.

Where an upstream project or another open-source project provides something useful, Max can borrow or adapt the relevant approach. It does not need to inherit every feature, dependency, architectural decision, or source of complexity.

## Contributing

Contributions are welcome — see CONTRIBUTING.md.

Commits must be signed off under the DCO (git commit -s). There is no CLA.
## License

Max is released under the [MIT License](LICENSE).

© 2026 Orkun Soylu © 2026 David Rutland

Icons by Lucide (ISC). Typeface: JetBrains Mono Nerd Font (SIL OFL 1.1). Full attribution for bundled third-party assets is in THIRD-PARTY-NOTICES.md.
