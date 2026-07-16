# Contributing

Thank you for improving Form 7 PDF Parser.

## Privacy first

Never commit or attach production shipping documents, extracted text, names, addresses,
phone numbers, payment details, or active tracking numbers. Bug reports must use fictional
data and a newly generated minimal PDF.

## Development workflow

1. Fork the repository and create a focused branch.
2. Create a virtual environment with Python 3.11 or newer.
3. Install development dependencies with `python -m pip install -e ".[dev]"`.
4. Add or update synthetic tests.
5. Run all checks listed below.
6. Give the pull request a Conventional Commit title.
7. Open the pull request with behavior, compatibility, release, and privacy impact.

```bash
ruff format --check .
ruff check .
mypy
pytest
python -m build
twine check dist/*
```

## Commits and releases

The repository uses squash merges. Pull request titles become the commits on `main`, so they
must follow `type(scope?): lowercase summary`. Use `fix:` or `docs:` for patches, `feat:` for
minor releases, and `!` or a `BREAKING CHANGE:` footer for major releases. See the
[release process](docs/release-process.md) for examples and recovery guidance.

Describe public API and JSON schema changes in the pull request. Release Please updates the
version and changelog from the Conventional Commit history. Breaking changes are reserved for
a new major version after `1.0.0`.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
