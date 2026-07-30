# Security Policy

M110 is a **local desktop application**. It runs with your own user privileges —
no daemon, no elevated helper, no listening socket — and it manages files in a
data folder you choose. Nothing is stored in the cloud, and no account is
involved.

That keeps the surface small, but it isn't zero, and two areas are worth
understanding before you use them: **what leaves your machine**, and **what the
AI assistant can see and do**. Both are covered below.

The engineering-side threat model lives in
[`docs-archive/SECURITY_ASSESSMENT.md`](docs-archive/SECURITY_ASSESSMENT.md) — a
point-in-time review (refreshed 2026-07-30) covering attack surface, findings, and
the build pipeline, including the assistant.

## What leaves your machine

Every network call M110 makes is listed here. There are no others, and none of
them send your images or library except where stated.

| What | When it runs | Where it goes |
|---|---|---|
| **Update check** | On launch, at most once a day — **on by default** | `api.github.com` — asks for this project's release list. Sends nothing about you; degrades silently when offline. Turn it off in Preferences → Updates. |
| **Object lookup** (Add object, Enrich online) | Only when you invoke it | [Simbad](https://simbad.cds.unistra.fr/) — sends the object name or designation you're looking up. |
| **Location lookup** (site profile → "Look up location…") | Only when you click it | [Nominatim](https://nominatim.openstreetmap.org/) — sends the place name you typed. That's a third party learning roughly where you observe, so it's an explicit action, never automatic. |
| **Publish → GitHub Pages** | Only when you publish to that target | Your own GitHub repository — **this one does upload images and text**. See [Publishing](#publishing). |
| **Report a problem / crash report** | Only when you choose to submit | Opens a prefilled GitHub issue in your browser. You see and edit the contents first. |

The object and location lookups need `astroquery`, which **packaged builds
include**. (Installing from source, it comes with the optional `online` extra —
`pip install 'm110[online]'`.) Either way, availability is not the control: these
lookups run only when you explicitly ask for them, and M110 makes no background
metadata queries.

## The AI assistant

M110 can expose your library to an AI client (Claude Desktop or another MCP
client) through a local **MCP server**. This is the largest privacy decision in
the app, so it's opt-in, and connecting a client shows you a plain-language
disclosure first.

**What the client can see.** A small, fixed set of tools (15 at time of writing)
covering your object list and per-object detail, journal notes, capture and
processing history, saved plans, target ranking, observability calculations,
and — on request — **rendered image data**. If a tool returns it, the client can
send it to whatever model it uses. That model is the client's choice, not
M110's; M110 holds no API key and makes no model calls itself.

**How it runs.** The server speaks [MCP](https://modelcontextprotocol.io) over
stdio — it is started by the client as a child process and talks over pipes.
**It does not open a network port**, so nothing on your network or the internet
can reach it. It runs as you, with your file permissions, against the data folder
it was configured with.

**What it can change: almost nothing, by construction.** No tool modifies or
deletes anything. A tool may **create** a new file, and only inside a staging
folder — the *outbox*, at
`.m110_internal_data/assistant/outbox` — with containment re-checked after path
resolution (so traversal, absolute paths, and outward symlinks all fail closed)
and a quota so a looping model can't fill your disk. Nothing in the outbox is
authoritative: M110 reads none of it until you accept an item in the app, backups
skip it, and deleting the folder loses only pending suggestions.

Suggested *changes* — pins, scoring weights, journal entries — are returned as
**proposals**, which are output, not actions. Applying one is your click.

**One opt-in widens this:** turning on direct-save lets a field guide the
assistant drafts skip staging and land in your `Plans/` folder as a new file. It
still only creates.

If you find a way to make an assistant tool modify or delete anything outside the
outbox, that is a security bug and we want the report.

## Publishing

**Publishing to a local folder** writes a rendered static site to a folder you
pick. Nothing is uploaded.

**Publishing to GitHub Pages uploads.** The rendered site — object pages,
journals, and **your images** — is pushed to a `gh-pages` branch in the
repository you name, which is public if that repository is public. Before you
publish, the dialog controls what's included: which sections, whether journals
are excluded, and a gallery level that defaults to **finished images only**
(working files stay off the site). Individual objects can be held back with a
`private: true` flag in their journal.

Uploading uses **your system `git`** and therefore your existing SSH key or
credential helper. M110 never sees, requests, or stores a token for it.

## Handling of secrets

**M110 stores no credentials or tokens today.** There is no password, no API key,
and no auth token anywhere in the data store or settings — the one remote target
that exists delegates authentication to your own git setup, and the assistant
delegates model access to your MCP client.

If a future publishing target requires M110 to hold a credential itself, it will
be stored in the **OS-native secure store** (macOS Keychain, Windows Credential
Manager, Linux Secret Service via `keyring`) rather than plaintext config, scoped
to the minimum permission the target needs, and **never** written to the data
store, logs (`~/.m110/logs/`), crash reports, or published output.

If you spot a case where a secret could leak into any of those, that's exactly
the kind of report we want.

## Untrusted files

M110 imports and parses files from places you don't fully control — an
SMB-mounted Seestar, a DwarfLab SD card, any folder you browse to. FITS headers
and image bytes from those files drive classification and destination paths, so
that's the most interesting boundary in the app for a researcher. Imports are
preview-then-confirm, every write is resolved and refused if it lands outside
your data folder, and image decoding is bounded against decompression bombs. A
crafted capture file that defeats any of those is a genuine finding.

## Supported versions

M110 is pre-1.0 and in active beta. Only the **latest release** (and `main`)
receives security fixes. Please reproduce on the latest version before reporting.

## Reporting a vulnerability

**Please do not open a public issue for a security vulnerability.**

Report privately instead, via either:

- **GitHub private advisory** — the [Security tab](https://github.com/mjm1138/m110/security/advisories/new)
  → "Report a vulnerability" (preferred; keeps the report and fix coordinated), or
- **Email** — **mjm1138@gmail.com** with a subject line starting `[M110 SECURITY]`.

Please include:

- The M110 version and your OS.
- A description of the issue and its impact.
- Steps to reproduce (a minimal case is ideal).
- Any relevant logs (`~/.m110/logs/m110.log`) — **redact file paths or personal
  data** you don't want shared.

## What to expect

- An acknowledgement, typically within a few days (this is a solo-maintained
  project, so response times are best-effort).
- An assessment of severity and, if confirmed, a fix on the next release.
- **Plain disclosure if it affected users.** M110 is open source; a security fix
  that mattered to you gets a `### Security` entry in
  [`CHANGELOG.md`](CHANGELOG.md) naming the vector and the real impact in your
  terms — not a vague "hardening" line, and not omitted because the bug was ours.
- Credit in the release notes for the disclosure, unless you prefer to remain
  anonymous.

Thank you for helping keep M110 and its users safe.
