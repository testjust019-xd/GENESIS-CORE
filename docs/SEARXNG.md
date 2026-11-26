# SearXNG setup

GENESIS can use a self-hosted SearXNG instance as its optional web search provider. Search results remain untrusted until reviewed in GENESIS. Page retrieval and source review continue to use the existing bounded research workflow.

## Configure in Studio

Open GENESIS Studio and use **Search Provider** in the right-hand panel:

1. Select **Self-hosted SearXNG**.
2. Enter the base URL of your instance, for example `http://127.0.0.1:8080`.
3. Save the settings.

The SearXNG instance must expose its JSON search format. GENESIS requests `/search?q=...&format=json&categories=general`.

## Configure from the terminal

For a local instance:

```bash
genesis search set searxng --url http://127.0.0.1:8080
genesis search show
```

A remote instance must use HTTPS:

```bash
genesis search set searxng --url https://search.example.org
```

To return to local-only research:

```bash
genesis search set offline
```

## Configuration precedence

Environment variables override the saved settings:

- `GENESIS_SEARCH_PROVIDER=searxng|brave|offline`
- `GENESIS_SEARXNG_URL=https://...`

Saved settings live in `$GENESIS_HOME/config/settings.json` under `research`. The default is offline local-knowledge search. GENESIS does not install, start, or administer SearXNG for you.

## Privacy and safety notes

- Self-hosting keeps the search gateway under your control, but queries still reach the external search engines configured inside SearXNG.
- Do not expose an unauthenticated SearXNG instance to the public Internet.
- Search snippets are untrusted. Review sources before generating a cited synthesis.
- GENESIS page fetching is separately bounded and validates public HTTP(S) destinations.
