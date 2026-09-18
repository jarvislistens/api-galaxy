# Privacy

The short version: **nothing leaves your machine unless you explicitly approve it, and
before you approve it you see exactly what would go.**

This document says precisely what that means, because a privacy promise you cannot verify
is a marketing claim.

## What runs where

| Thing | Where it happens |
| --- | --- |
| Parsing your specification | Your machine |
| Building the graph | Your machine |
| All 15 deterministic rules | Your machine |
| Alias detection | Your machine |
| Journey derivation and validation | Your machine |
| Change impact | Your machine |
| Every export | Your machine |
| Ask, with the deterministic provider | Your machine |
| Ask / enrichment, with Ollama | Your machine |
| Ask / enrichment, with Kimi | **The provider's servers**, after you consent |

The application binds to `127.0.0.1` by default. It makes no outbound request at all
unless you configure an external provider *and* approve a payload for that project.

## The external-provider path, step by step

1. **It is off until you add a key.** No key, no external calls. There is also a master
   switch in Settings that disables external providers entirely, and turning it off clears
   every consent you have given.
2. **Your payload is sanitised.** Before anything is prepared for sending, it passes
   through the redaction rules below, and example values, default values and server
   declarations are dropped wholesale.
3. **You see a preview.** The Ask and Arena screens show the exact payload plus a summary
   of what was removed — "Removed 3× email, 1× api key assignment, 12 example values".
4. **You consent, per project.** Agreeing to send a public sample says nothing about
   agreeing to send your employer's internal specification. You can tick "remember for
   this project", and you can revoke it.
5. **Only the minimum goes.** The model never receives your whole project — it receives a
   bounded, chunked slice with an explicit list of the node IDs it is allowed to cite.
6. **We record the metadata, not the content.** The decision log stores the provider,
   model, prompt template version, a payload fingerprint and token counts. Never the
   payload, never a secret.

## What gets redacted

Every rule below runs on any text that could leave the machine. All of them are covered by
tests in `tests/unit/test_providers.py`.

| Rule | Catches |
| --- | --- |
| `private_key` | PEM private key blocks |
| `jwt` | JSON Web Tokens |
| `bearer` | `Authorization: Bearer …`, `token: …` |
| `api_key_assignment` | `api_key=`, `client_secret=`, `password=`, `access_token=`… |
| `aws_key` | `AKIA…` / `ASIA…` access key IDs |
| `slack_token`, `github_token`, `openai_key` | provider-specific token shapes |
| `email` | email addresses |
| `phone` | telephone numbers |
| `card` | 13–19 digit payment card numbers |
| `cookie` | `Cookie:` / `Set-Cookie:` values |
| `private_host` | `localhost`, RFC1918 addresses, `*.local`, `*.internal`, `*.corp`… |
| `env_var` | `SHOUTY_NAME=value` assignments |

Dropped wholesale, not pattern-matched: `example`, `examples`, `default`, `enum`,
`servers`, and anything keyed `password`, `secret`, `token`, `apikey`, `authorization`,
`cookie`, `credentials`, `x-internal`, `x-secret`.

Two deliberate details:

* **Card before phone.** A 16-digit card number also satisfies the phone pattern, and
  whichever rule runs first consumes it — so the more sensitive classification goes first.
* **ISO dates are exempt from the phone rule.** `2026-09-19` otherwise matches, and
  silently deleting every date from a specification's prose makes the model's context
  worse for no privacy gain.

Redaction is deliberately over-eager. If it removes something harmless, you lose a little
context quality. The opposite mistake is unrecoverable.

## Where your data is stored

`~/.api-galaxy` by default (`API_GALAXY_DATA_DIR` overrides it):

```
api-galaxy.sqlite     projects, scenarios, jobs, settings, exports, decision log
projects/<id>/        graph.json, estate.json, risks.json, journeys.json, aliases.json
exports/<id>/         generated reports
```

Plain files. Delete the directory and API Galaxy has forgotten you. Settings →
**Clear all local data** does the same from inside the app and reports what it removed.

## Secrets

If `keyring` is installed, an external API key goes to your OS keychain. If it is not, the
key lives in process memory for the session only and is gone on restart. The Settings
screen tells you which of the two is happening — it does not imply the stronger one.

Keys are never written to SQLite, never written to a file, and never logged.

## Network safety

* Remote `$ref` resolution is **off by default**. Turning it on lets a specification pull
  content from the internet at parse time.
* URL import is guarded against SSRF: HTTPS only, and every address the hostname resolves
  to is checked, so a public name pointing at `127.0.0.1` is still refused. Private and
  loopback ranges are blocked unless you explicitly enable them.
* Uploads are size-capped, type-checked and filename-sanitised. YAML is loaded with
  `yaml.safe_load` only — never `yaml.load`.

## What we do not do

No telemetry. No analytics. No crash reporting. No update check. No account. No cloud
sync. There is no server to phone home to.
