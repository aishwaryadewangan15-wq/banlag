# Security policy

## Supported versions

Security fixes go to the latest commit on `main`.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Use GitHub's private reporting instead: **Security → Report a vulnerability** on this repository.

Include the affected file or endpoint, steps to reproduce, and the impact. You should get an acknowledgement within 7 days.

## Scope

In scope:

- The local server (`banlag/server.py`): host checks, cross-origin protection, request limits, path handling, CSP.
- Capture integrity (`banlag/capture_store.py`, `banlag/collector.py`): seal forgery, origin upgrade, API-key leakage into captures or logs.
- Import handling: any way user-supplied evidence can be shown as trusted SerpApi evidence.

Out of scope: problems that need an attacker who already controls the local machine or the HMAC key file.

## Secrets

Never commit a SerpApi key or the capture HMAC key. The key lives outside the repository (`%LOCALAPPDATA%\BANLAG\` on Windows, `$XDG_DATA_HOME/banlag` elsewhere), and the store refuses keys inside the project or a synced folder.
