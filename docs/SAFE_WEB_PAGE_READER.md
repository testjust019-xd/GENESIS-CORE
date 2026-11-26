# Safe web page reader — Initial

GENESIS Research can now retrieve and extract readable text from public web pages
after a search result has been saved to the source vault.

## API

- `POST /api/research/sources/{source_id}/fetch` retrieves and stores page text.
- `GET /api/research/sources/{source_id}/page` returns the stored extraction.

The Studio Research panel exposes a **Read page** action for each source. Extracted
text is displayed as text, not interpreted as HTML.

## Limits and protections

- HTTP(S) only; standard ports 80 and 443.
- Hostnames are resolved and private, loopback, link-local and reserved addresses
  are rejected.
- Every redirect destination is validated; at most three redirects are followed.
- Ten-second request timeout and 1.5 MB response limit.
- Only HTML, XHTML and plain text are accepted.
- Script, style, SVG, canvas, template and noscript content is excluded.
- Extracted text is capped at 80,000 characters and stored in SQLite.
- Rejected sources cannot be fetched.
- Page content remains untrusted evidence and is never treated as agent instructions.
- Existing research databases are migrated to add the page fields.

## Current limitations

This is a bounded text extractor, not a full browser. It does not execute JavaScript,
log in, download arbitrary files, render pages, or bypass paywalls. Sites that rely
on client-side rendering may produce little or no extracted text. DNS rebinding
protection is best-effort in this initial implementation; production hardening
should pin the validated resolved address to the connection.
