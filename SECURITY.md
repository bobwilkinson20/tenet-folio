# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in TenetFolio, please report it responsibly.

**Do NOT open a public GitHub issue for security vulnerabilities.**

### How to Report

1. **GitHub Security Advisory (preferred):** Use [GitHub's private security advisory feature](https://github.com/bobwilkinson20/tenet-folio/security/advisories/new) to report the issue confidentially.
2. **Email:** Contact the maintainer directly at the email listed on the [GitHub profile](https://github.com/bobwilkinson20).

### What to Include

- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

## Scope

This policy covers the TenetFolio application itself, including:

- Backend API (FastAPI)
- Frontend application (React)
- Database handling and migrations
- Authentication and credential management

**Out of scope:** Vulnerabilities in upstream brokerage providers (SnapTrade, SimpleFIN, Interactive Brokers, Coinbase, Charles Schwab), their APIs, or third-party dependencies (report those to the respective projects).

## Response

- Acknowledgment within 48 hours
- Status update within 7 days
- Fix timeline depends on severity, but we aim to address critical issues promptly

## Supported Versions

Only the latest version on the `main` branch is actively supported with security updates.
