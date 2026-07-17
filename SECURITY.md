# Security Policy

## Supported versions

Security fixes are provided for the latest minor release.

| Version | Supported |
| --- | --- |
| 0.2.x | Yes |
| 0.1.x | No |
| Older | No |

## Reporting a vulnerability

Use GitHub private vulnerability reporting for this repository. Do not open a public issue
for a suspected vulnerability.

Never include real shipping PDFs, extracted personal data, credentials, addresses, phone
numbers, or active tracking numbers in a report. Create a synthetic reproduction instead.

You can expect an initial response within seven days. Reports will be assessed for impact,
reproducibility, and affected versions before a coordinated fix is prepared.

## Security boundaries

This package parses complex PDF input and should not be treated as a security sandbox. For
untrusted files, run it in an isolated process with CPU, memory, file-size, and execution-time
limits. The package performs no network requests or telemetry.
