# Changelog

All notable changes to this project are documented in this file.

The format follows Keep a Changelog 1.1.0, and the project uses Semantic Versioning 2.0.0.

## [0.2.1](https://github.com/alyldas/form7-pdf-parser/compare/v0.2.0...v0.2.1) (2026-07-17)


### Bug Fixes

* **ci:** replaced invalid pip-audit action ref ([#11](https://github.com/alyldas/form7-pdf-parser/issues/11)) ([0bf42c7](https://github.com/alyldas/form7-pdf-parser/commit/0bf42c7fc3ddbb71cc05f186a3b707cd7beb6b37))
* harden PDF input boundaries ([#7](https://github.com/alyldas/form7-pdf-parser/issues/7)) ([1ff19ac](https://github.com/alyldas/form7-pdf-parser/commit/1ff19ac9bfc1b2f88992f7ec2bc0db71ba477bd4))
* hardened parser and PDF reliability ([#10](https://github.com/alyldas/form7-pdf-parser/issues/10)) ([173bd83](https://github.com/alyldas/form7-pdf-parser/commit/173bd83602f2568e4d33b1ecef8afff47e04390d))
* hardened PDF annotation and input boundaries ([#9](https://github.com/alyldas/form7-pdf-parser/issues/9)) ([ba5d6d9](https://github.com/alyldas/form7-pdf-parser/commit/ba5d6d9eae79920b554b5baaf6d407274a6ce08a))

## [0.2.0](https://github.com/alyldas/form7-pdf-parser/compare/v0.1.0...v0.2.0) (2026-07-16)


### Features

* **parser:** added validation issues and preserved overlay labels ([#3](https://github.com/alyldas/form7-pdf-parser/issues/3)) ([b903033](https://github.com/alyldas/form7-pdf-parser/commit/b9030339aa4841380fd189e1be0b4b4a8a61c191))


### Bug Fixes

* **release:** made release automation retry-safe ([#6](https://github.com/alyldas/form7-pdf-parser/issues/6)) ([8c00c45](https://github.com/alyldas/form7-pdf-parser/commit/8c00c4511311d3fba6b0efc842597a82ade06c9a))

## [Unreleased]

### Added

- Cross-platform smoke tests and regression coverage for noisy extracted text, CropBox layouts,
  rotated pages, atomic directory synchronization, and byte-identical PDF copies.
- Public API documentation for parser, annotation, models, limits, and privacy behavior.

### Changed

- PDF inputs are opened once and validated through one shared size, page, and encryption path.
- Overlay labels now shrink to the visible page area and empty overlays use a fast copy path.
- Shared CLI limit arguments and platform-specific output permission guarantees are documented.

### Fixed

- Numeric service lines can no longer shift split tracking-number groups.
- Tax identifiers and unsupported numeric fields are no longer accepted as phone lines.
- Labels now respect CropBox origins and page rotation instead of overflowing or moving off-page.

## [0.1.0] - 2026-07-15

### Added

- Typed Python API for parsing text-based Form 7 PDFs.
- Privacy-safe CLI with atomic owner-only output files.
- PDF page annotation through public `pypdf` and ReportLab APIs.
- Synthetic test fixtures, CI, packaging checks, and community health files.
