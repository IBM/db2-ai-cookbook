# Security

## Reporting a vulnerability

Please report security issues **privately**, not in a public issue — a public report advertises the
problem before it can be fixed, and a leaked credential in an issue is worse than the leak itself.

Use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, or contact the maintainer directly.

If you find a credential committed anywhere in this repository or its history, report it privately
and it will be revoked and rotated.

## What this repository is

These are **teaching recipes**, not production software. They are written to make the moving parts
visible, which means they deliberately skip hardening you would want in a real deployment:

- **Local services run with security disabled.** OpenSearch, llama.cpp servers and similar bind to
  `127.0.0.1` with authentication off, because a recipe should be one command to start. Do not
  copy those settings onto a shared or public network.
- **SQL is built with string interpolation** in some notebooks, so a query and its parameters read
  as one thing. Use parameter markers in code that takes untrusted input.
- **Errors are unhandled** by design. A recipe that swallows exceptions teaches nothing; a
  traceback shows you exactly which step failed.

Treat every recipe as a starting point to learn from, not a template to deploy.

## Credentials

No recipe should ever require a credential in a tracked file.

- Real values belong in `.env`, which is git-ignored — along with `.env.*`, so that a `.env.bak`
  copy cannot slip through either.
- Every recipe that needs configuration commits a `.env.example` with placeholder values.
- Use scoped, disposable API keys where the provider supports them, and revoke them when you are
  finished with a recipe.
