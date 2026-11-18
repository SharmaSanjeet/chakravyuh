# Security Policy

Chakravyuh AI is a **defensive** tool (honeypot/deception). We welcome responsible
disclosure of vulnerabilities.

## Reporting a vulnerability

- **Do not** open a public issue.
- Use the repository's private **GitHub Security Advisories**
  (the *Security → Report a vulnerability* tab).
- Include version/commit, reproduction steps, and impact. We respond as soon as
  possible and coordinate disclosure after a fix.

## Threat model and design decisions

By definition, Chakravyuh is deployed in hostile environments. Key assumptions:

- The **honeypot is attacked on purpose**. The lure content (AWS/JWT/DB keys, decoy
  binaries) is **inert**: it matches no real credentials and executes nothing.
- **Remote sensors** may live on servers that end up compromised. That is why their
  key is **least-privilege** (ingestion + control of their own sensor only),
  **revocable/rotatable** with one click, and ingestion is always treated as
  **hostile** (validation, rate limiting, dedup, prefix filtering).
- The sensor↔server channel uses **HMAC signatures in both directions** (including
  the control responses) plus an anti-replay window, so a MITM cannot forge
  submissions or shutdown orders. Deploy the server behind **TLS**.
- Agentless mode sends **only the lure lines** (prefix filter) so it never exfiltrates
  real user traffic; use the **dry-run** before enabling it.

## Responsible use

Deploy sensors only on infrastructure you are **authorized** to protect.
Isolate the lure path from the real paths and apply the secure-serving config included
in each bundle (serve the content as data, never as code).
