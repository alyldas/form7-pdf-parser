# Contributing

Thank you for improving Form 7 PDF Parser.

## Privacy first

Never commit or attach production shipping documents, extracted text, names, addresses,
phone numbers, payment details, or active tracking numbers. Bug reports must use fictional
data and a newly generated minimal PDF.

## Development workflow

1. Clone your fork, enter the repository directory and create a focused branch.
2. Create a virtual environment with Python 3.11 or newer:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   python -m pip install -e ".[dev]"
   ```

3. Read the [format reference](docs/formats.md) before changing parsing or placement rules.
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

## Code map and compatibility

- `parsing.py` contains text heuristics. `parse_page` selects the format once and
  retains recipient diagnostics from the same extraction as its fields. Public
  lower-level helpers use those same format-specific functions. Waybill phone spans
  and the routing-postcode boundary are handled in one pass, without reparsing numbers.
- `pdf.py` owns bounded input reading; `annotation.py` owns label placement and
  occupied-area checks. The overlay font is registered only when labels are added.
- `atomic.py` owns output publication: close the writer to flush its buffers,
  sync the completed file, then replace.
  An error before replacement must leave existing output intact.
- `models.py` defines results and the stable JSON shape; `cli.py` handles arguments
  and JSON input. Preserve public signatures, JSON fields and diagnostic ordering.

Use fictional data for regression tests. See the
[fixture guide](tests/fixtures/README.md) for generating synthetic PDFs. Placement
changes must retain coverage for rotation, CropBox offsets and occupied areas.

## Commits and releases

The repository uses squash merges. Pull request titles become the commits on `main`, so they
must follow `type(scope?): lowercase summary`. Use `fix:` or `docs:` for patches, `feat:` for
minor releases, and `!` or a `BREAKING CHANGE:` footer for major releases. See the
[release process](docs/release-process.md) for examples and recovery guidance.

Describe public API and JSON schema changes in the pull request. Release Please updates the
version and changelog from the Conventional Commit history. Breaking changes are reserved for
a new major version after `1.0.0`.

By participating, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
