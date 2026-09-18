# Security

## Reporting a vulnerability

Please do **not** open a public issue. Email the repository owner with a description, the
version, and a reproduction if you have one. You will get an acknowledgement, and credit
in the fix unless you would rather not have it.

## What this software is

A local-first desktop-style application. It binds to `127.0.0.1`, has no authentication
and no multi-user model, because there is no server and no second user. **Do not expose it
to a network.** If you bind it to `0.0.0.0`, you are giving everyone who can reach that
port the ability to read every specification you have imported and to spend your API key.

## Threat model

What this application defends against:

| Threat | Defence |
| --- | --- |
| A malicious specification causing code execution | `yaml.safe_load` only, never `yaml.load`. Nothing from a document is evaluated. |
| A specification causing unbounded resource use | Size caps, `$ref` depth cap, field-count cap, node/edge/depth/time limits on every traversal. |
| A specification reaching your internal network | Remote `$ref` resolution is off by default. URL import is SSRF-guarded: HTTPS only, and every resolved address is checked, so a public hostname pointing at `127.0.0.1` is still refused. |
| Secrets leaking to a third-party model | Sanitisation before every external call, plus per-project consent, plus a master off switch. See `docs/privacy.md`. |
| A model emitting something executable | Model output is parsed as JSON against a fixed schema. Cypher, SQL, shell, JavaScript and Python are never accepted for execution, and repair `kind` values are whitelisted. |
| An uploaded filename escaping the data directory | Filenames are stripped of directory components and sanitised; export downloads re-check that the resolved path is inside the exports directory before serving it. |
| A crafted schema name breaking the HTML report | All project data is escaped; the DOM is built with `textContent`, never `innerHTML`; `</script>` is neutralised inside the embedded JSON; a `<meta>` CSP of `default-src 'none'` backs it up. |
| Injection into an exported Mermaid diagram | `<` and `>` are escaped in labels — Mermaid renders labels as HTML by default. |
| CSV formula injection | Cells beginning `=`, `+`, `-`, `@`, tab or CR are prefixed with a quote. |
| A runaway client pinning the machine | Per-client request rate limit. |

What it explicitly does **not** defend against:

* An attacker with read access to your filesystem. Projects are plain JSON files.
* An attacker who can modify the SQLite database.
* A malicious `cytoscape`, `fastapi` or other dependency. Standard supply-chain risk.
* You choosing to send a confidential specification to an external provider. The consent
  dialog shows you what would be sent; the decision is yours.

## Secrets

External API keys go to the OS keychain when `keyring` is installed, and otherwise live in
process memory for the session only. They are **never** written to SQLite, never written to
a file, and never logged. Settings states which of the two is in effect rather than
implying the stronger one.

`.env` is gitignored. If you put a key there, it is on your disk in plaintext — the
Settings field is the better path.

## Dependency policy

Dependencies are chosen for being widely used and actively maintained. Optional heavy ones
(`weasyprint`, `cairosvg`, `keyring`) are genuinely optional: without them the affected
feature reports itself unavailable with the reason, rather than degrading silently.

## Hardening checklist, if you must run this somewhere shared

1. Put it behind an authenticating reverse proxy. There is no auth in the app.
2. Set `API_GALAXY_EXTERNAL_PROVIDERS_ENABLED=false`.
3. Leave `API_GALAXY_ALLOW_REMOTE_REFS` and `API_GALAXY_ALLOW_PRIVATE_NETWORK_URLS` false.
4. Give the process its own user and its own `API_GALAXY_DATA_DIR`.
5. Lower `API_GALAXY_MAX_UPLOAD_BYTES` and `API_GALAXY_REQUEST_RATE_LIMIT_PER_MINUTE`.

Even then: this was built as a local tool, and that is where it is safe.
