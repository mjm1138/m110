# Security Policy

M110 is a **local desktop application**. It manages files on your own machine and
does not run a server or store your data in the cloud. Its network use is limited
and optional — object-metadata lookups against [Simbad](https://simbad.cds.unistra.fr/)
for the "Add object" / "Enrich online" features, which are off by default and only
active when the optional `online` extra is installed. It never uploads your images
or library.

Because of that, the security surface is small — but we still take reports
seriously.

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
- Credit in the release notes for the disclosure, unless you prefer to remain
  anonymous.

Thank you for helping keep M110 and its users safe.
