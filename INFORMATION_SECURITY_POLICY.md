# Information Security Policy

**Effective Date: February 19, 2026**
**Last Reviewed: February 19, 2026**

## 1. Purpose

This document defines TenetFolio's information security policy — the controls, practices, and architectural decisions that protect user financial data. It is intended for third-party security assessments (e.g., data aggregation provider questionnaires) and for users who want to understand how their data is secured.

## 2. Scope

This policy applies to the TenetFolio application, including:

- Backend API (FastAPI / Python)
- Frontend application (React / TypeScript)
- Local SQLite database (optionally encrypted with SQLCipher)
- Credential storage (macOS Keychain, environment variables)
- Integrations with third-party financial data providers

## 3. Architecture Overview

TenetFolio is a **local-first, single-user** application. All components run on the user's own machine:

- **No cloud infrastructure.** There are no central servers, cloud databases, or hosted services.
- **No network exposure.** The application binds to `localhost` only. It is not accessible from the network.
- **No user accounts or authentication.** There is no multi-tenancy. The operator is the sole user.
- **No telemetry.** There are no analytics, tracking, or "phone-home" capabilities.

This architecture eliminates entire categories of risk — there is no server to breach, no database to exfiltrate remotely, and no user credentials to compromise at scale.

## 4. Data Classification

| Classification | Examples | Handling |
|---------------|----------|----------|
| **Sensitive Credentials** | API keys, OAuth tokens, access URLs, SQLCipher encryption key | macOS Keychain (preferred) or local `.env` file. Never committed to source control. Never transmitted to the developer. |
| **Financial Data** | Holdings, account balances, transaction history, net worth | Stored locally in SQLite database. Optionally encrypted at rest with SQLCipher. Never leaves the user's machine. |
| **Configuration** | Database path, environment setting, feature flags | Local `.env` file. Non-sensitive. |
| **Application Code** | Source code, dependencies | Open source. Publicly auditable on GitHub. |

## 5. Credential Management

### 5.1 Storage

Credentials are stored using a priority hierarchy:

1. **macOS Keychain** (preferred) — OS-level encrypted credential storage, protected by the user's system password and Secure Enclave where available.
2. **Environment variables / `.env` file** (fallback) — local file excluded from version control via `.gitignore`.

The application never stores credentials in source code, database tables, or log files.

### 5.2 Credential Inventory

| Credential | Provider | Storage | Access Pattern |
|-----------|----------|---------|---------------|
| App keys and secrets | Plaid, SnapTrade, Schwab, Coinbase | Keychain or `.env` | Read at startup |
| OAuth tokens | Plaid, Schwab | Keychain or Local JSON file (path in Keychain/`.env`) | Read/refresh at runtime |
| Access URLs | SimpleFIN | Keychain or `.env` | Read at sync time |
| Flex tokens | Interactive Brokers | Keychain or `.env` | Read at sync time |
| SQLCipher key | Local | Keychain only | Read at database open |

### 5.3 Credential Rotation

- **Schwab OAuth tokens** expire every ~7 days and are refreshed via a dedicated script.
- **Plaid access tokens** are long-lived but can be rotated on-demand or invalidated.
- **SnapTrade user secrets** are long-lived but can be regenerated via SnapTrade's dashboard.
- **SimpleFIN access URLs** are permanent but revocable by the user at any time via SimpleFIN Bridge.
- **SQLCipher key** is generated once on first run and does not expire. Users are advised to back up this key, as loss results in an unrecoverable database.

## 6. Encryption

### 6.1 At Rest

- **Database encryption:** SQLite databases can be encrypted with SQLCipher (AES-256-CBC). The encryption key is stored in macOS Keychain and is auto-generated on first run.
- **Credential encryption:** Credentials in macOS Keychain are encrypted by the OS using hardware-backed keys where available.

### 6.2 In Transit

- **Provider APIs:** All communication with financial data providers uses HTTPS/TLS. No plaintext API calls are made.
- **Local communication:** Frontend-to-backend communication occurs over `localhost` (HTTP) and does not traverse any network.

## 7. Access Control

### 7.1 Application Access

The application runs locally and binds to `localhost` only. There is no remote access, no authentication layer, and no user management — the person running the application is the sole user with full access.

### 7.2 Provider Access

All brokerage integrations use **read-only** API access:

- Plaid: Read-only account and holding data
- SnapTrade: Read-only portfolio data
- SimpleFIN: Read-only account and holding data
- Interactive Brokers: Read-only Flex Query reports
- Coinbase: "View" permission only
- Schwab: Read-only account and position data

No integration has the ability to execute trades, transfer funds, or modify account settings.

### 7.3 Source Code Access

The codebase is open source. Changes to the `main` branch require pull request review. All commits are attributed.

## 8. Secure Development Lifecycle

### 8.1 Code Quality

- **Linting:** Backend code is checked with Ruff; frontend with ESLint and TypeScript strict mode.
- **Type safety:** Python type hints (enforced by tooling) and TypeScript strict compilation catch errors at build time.
- **Testing:** 1500+ backend tests and 450+ frontend tests run on every change. All tests must pass before merging.
- **CI pipeline:** Automated checks (lint, type-check, test suite) run on every pull request via GitHub Actions.

### 8.2 Dependency Management

- Dependencies are pinned via `uv.lock` (backend) and `package-lock.json` (frontend).
- GitHub Dependabot monitors for known vulnerabilities in dependencies and opens automated pull requests for updates.

### 8.3 Security-Conscious Coding Practices

- No raw SQL construction from user input (SQLAlchemy ORM with parameterized queries).
- No dynamic HTML rendering from user input (React's default XSS protection).
- No secrets in source code (enforced by `.gitignore` patterns and code review).
- Error responses do not leak internal details (stack traces, database paths, credential values).

## 9. Risk Assessment

### 9.1 Threat Model

Given the local-first architecture, the primary risks are:

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Local machine compromise | Low–Medium | High | OS-level security (FileVault, Gatekeeper, Keychain). SQLCipher database encryption. |
| Credential exposure via `.env` file | Low | High | macOS Keychain preferred over `.env`. `.gitignore` prevents accidental commit. |
| Malicious dependency (supply chain) | Low | High | Pinned dependencies. Dependabot alerts. Open-source audit trail. |
| Provider API breach | Low | Medium | Read-only access limits blast radius. Credentials revocable by user at any time. |
| SQLCipher key loss | Low | High | Key stored in Keychain with documented backup procedure. |

### 9.2 What Is Explicitly Out of Scope

- **Network attacks** (MITM, DDoS) — the application does not accept inbound connections.
- **Multi-user privilege escalation** — there is only one user.
- **Server-side data breach** — there is no server.

## 10. Incident Response

### 10.1 Vulnerability Reporting

External security researchers can report vulnerabilities via:

1. **GitHub Security Advisory** (preferred) — private, confidential reporting.
2. **Direct email** to the maintainer.

Full details are in [SECURITY.md](SECURITY.md).

### 10.2 Response Timeline

- **Acknowledgment:** Within 48 hours of report.
- **Triage and status update:** Within 7 days.
- **Fix:** Critical vulnerabilities are prioritized for immediate patch release.

### 10.3 Disclosure

Confirmed vulnerabilities are disclosed via GitHub Security Advisories after a fix is available. The project follows coordinated disclosure practices.

## 11. Data Retention and Disposal

- **Financial data** is retained locally indefinitely until the user deletes the database file or uninstalls the application.
- **No backups are made to external systems.** The user controls all backup and retention decisions.
- **Credential revocation:** Users can revoke provider access at any time through the respective provider's dashboard (SnapTrade, SimpleFIN Bridge, Schwab Developer Portal, IBKR Client Portal, Coinbase CDP).
- **Complete removal:** Deleting the application directory and its Keychain entries removes all data and credentials.

See [PRIVACY.md](PRIVACY.md) for the full data handling policy.

## 12. Third-Party Risk

TenetFolio integrates with external financial data providers. Risk is managed by:

- **Read-only access:** No provider integration can execute trades or move funds.
- **User-controlled credentials:** The user provisions and can revoke credentials at any time.
- **Direct communication:** Data flows directly from the provider API to the user's local machine. No intermediary servers.
- **Provider selection:** Users choose which providers to enable. No provider is required.

Each provider's own security posture, certifications, and data handling are governed by their respective policies and are outside the scope of this document.

## 13. Monitoring and Logging

- **Application logging:** All sync operations, API errors, and CRUD events are logged locally at INFO level using Python's `logging` module. Logs do not contain credentials or raw financial values.
- **No centralized log collection.** Logs remain on the user's machine.
- **Audit trail:** Every data sync creates a `SyncSession` record with per-provider and per-account status, enabling the user to review sync history.

## 14. Policy Review

This policy is reviewed and updated:

- At least annually.
- When significant architectural changes are made.
- When new provider integrations are added.

## Related Documents

- [SECURITY.md](SECURITY.md) — Vulnerability reporting and disclosure process
- [PRIVACY.md](PRIVACY.md) — Data collection, usage, and retention policy
- [ARCHITECTURE.md](docs/ARCHITECTURE.md) — Technical architecture overview
