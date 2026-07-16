# Changelog

All notable changes to this project are documented in this file.

The format follows Keep a Changelog 1.1.0, and the project uses Semantic Versioning 2.0.0.

## [Unreleased]

### Added

- Typed validation issues for invalid parsed pages without changing the JSON contract.
- A table-driven synthetic parsing corpus covering valid, partial, and invalid layouts.

### Changed

- Overlay labels now preserve allowed ASCII text around digits and reject normalized labels
  longer than 64 characters.

## [0.1.0] - 2026-07-15

### Added

- Typed Python API for parsing text-based Form 7 PDFs.
- Privacy-safe CLI with atomic owner-only output files.
- PDF page annotation through public `pypdf` and ReportLab APIs.
- Synthetic test fixtures, CI, packaging checks, and community health files.
