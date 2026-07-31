# Security Policy

## Supported versions

Security fixes are applied to the latest version on the `main` branch.

## Reporting a vulnerability

Please do not report vulnerabilities in a public issue. If the repository is hosted on GitHub, use its private security advisory feature. Include:

- the affected version or commit;
- clear reproduction steps;
- the expected impact;
- any suggested mitigation; and
- whether the report may be disclosed after a fix is available.

Do not include account cookies, private URLs, downloaded media, access tokens, or other personal data.

## Deployment scope

FluxDL is designed for a single user on a trusted machine and binds to `127.0.0.1` by default. It does not provide authentication, authorization, TLS termination, rate limiting, or multi-user isolation. Do not expose it directly to the public internet.
