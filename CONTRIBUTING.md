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
6. Open a pull request describing behavior, compatibility, and privacy impact.

```bash
ruff format --check .
ruff check .
mypy
pytest
python -m build
twine check dist/*
```

Changes to the public API or JSON schema must include a changelog entry. Breaking changes are
reserved for a new major version after `1.0.0`.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).

