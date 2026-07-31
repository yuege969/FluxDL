# Contributing to FluxDL

Thank you for helping improve FluxDL.

## Before you start

- Search existing issues before opening a new one.
- Use a clear title and include reproducible steps for bugs.
- Do not include private video URLs, cookies, account data, or downloaded media in reports.
- For security issues, follow [SECURITY.md](SECURITY.md) instead of opening a public issue.

## Development setup

```bash
git clone <your-fork-url>
cd fluxdl
uv sync
uv run fluxdl
```

FluxDL requires Python 3.10 or newer. Install FFmpeg to exercise media merging and subtitle features.

## Tests

Run the complete unit test suite before submitting a change:

```bash
uv run python -m unittest discover -s tests -v
```

Changes to download behavior should cover both FFmpeg-present and FFmpeg-absent paths where relevant. Keep tests offline and deterministic.

## Pull requests

1. Create a focused branch from `main`.
2. Keep each pull request limited to one logical change.
3. Add or update tests and documentation.
4. Explain user-visible behavior and any compatibility tradeoffs.
5. Confirm that no media, models, cookies, tokens, or local history are included.

By contributing, you agree that your contributions are licensed under the repository's MIT License.
