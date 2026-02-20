# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

### Changed
- Sync pipeline uses typed exception hierarchy (`ProviderAuthError`, `ProviderConnectionError`, `ProviderAPIError`, `ProviderDataError`) instead of bare `Exception` catches
- Provider errors are now structured (`ProviderSyncError` dataclass) with category, institution name, and retriable flag instead of plain strings
- SimpleFIN error parsing moved from sync service regex into the client itself
- API sync endpoint no longer leaks internal error messages (returns generic 500/502 responses)

### Fixed
- Replace `threading.Lock` with SQLite `BEGIN IMMEDIATE` for manual holdings operations, fixing a latent race condition with multi-worker deployments

## [0.1.0] - 2026-02-18

### Added
- Initial open-source release
- Multi-provider sync (SnapTrade, SimpleFIN, IBKR, Coinbase, Schwab)
- Portfolio dashboard with holdings and allocation views
- Daily valuation tracking with historical charts
- Asset classification system with waterfall logic
- SQLCipher database encryption support
- macOS Keychain credential storage
