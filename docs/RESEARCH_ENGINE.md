# Research Engine

The initial Research Engine is local-first and provider-agnostic.

## Modes

- **Offline:** if no web provider is configured, queries the local Knowledge Engine and stores matching excerpts as research sources.
- **SearXNG:** set `GENESIS_SEARCH_PROVIDER=searxng` and `GENESIS_SEARXNG_URL=https://your-searxng.example`. A local self-hosted instance may use HTTP on loopback.
- **Brave Search:** set `GENESIS_SEARCH_PROVIDER=brave` and `GENESIS_BRAVE_API_KEY` in the process environment.

No API key or external provider is required for offline mode. Provider calls have a timeout and bounded response size. Remote provider endpoints require HTTPS; local loopback is allowed for a self-hosted SearXNG service. Credentials must not be embedded in endpoint URLs.

## Source review

Every search result is stored in the local SQLite source vault with title, URL, snippet, provider, retrieval time and optional publication time. Sources begin as `pending`; users can mark them `approved` or `rejected`. A review decision is a human workflow state, not proof of objective truth. Repeated URLs are deduplicated and preserve their existing review state.

Search snippets and page metadata are untrusted data. The initial release stores snippets and links but does not fetch arbitrary result pages, execute page scripts, or follow instructions contained in results.

## TUI

- `/research search <query>`
- `/research sources [pending|approved|rejected]`
- `/research review <id> approve|reject`

## Studio API

- `POST /api/research/search` — JSON body: `{"query":"...", "limit":8}`
- `GET /api/research/runs`
- `GET /api/research/sources?review_status=pending`
- `POST /api/research/sources/{id}/review` — JSON body: `{"decision":"approved","note":"..."}`

## Current limitations

The first slice does not yet crawl result pages, extract full articles, verify claims across independent sources, or generate a cited research report. Search providers and network access are optional.
