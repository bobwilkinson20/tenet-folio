# Privacy Policy for TenetFolio

**Last Updated: February 17, 2026**

TenetFolio is an open-source, self-hosted personal portfolio management application. This Privacy Policy explains our commitment to your financial privacy and outlines how data is handled within the application.

## 1. Zero-Knowledge Architecture

TenetFolio is designed as a **local-first** application. This means:

- **No Central Servers:** The developer of TenetFolio does not operate any central servers, cloud databases, or data collection endpoints.
- **Local Storage:** All financial data, transaction histories, and portfolio metrics are stored locally on your own hardware in a SQLite database (optionally encrypted with SQLCipher).
- **Credential Security:** Your API keys, secrets, and session tokens (for Plaid, Schwab, IBKR, etc.) are stored in your local system keychain or a local environment file. These credentials are never transmitted to the developer.

## 2. Third-Party Integrations

TenetFolio acts as a local client that communicates directly with financial data providers. When you enable an integration, data is exchanged strictly between your local instance of TenetFolio and the respective provider's API using your accounts.

Supported integrations include, but are not limited to:

- **Aggregators:** Plaid, SimpleFIN, SnapTrade.
- **Direct Institutions:** Charles Schwab, Interactive Brokers (IBKR), Coinbase.

Your use of these third-party services is governed by their respective privacy policies and terms of service.

## 3. Data Usage & Sharing

- **Usage:** Data retrieved from financial institutions is used solely for local portfolio visualization, performance tracking, and asset allocation analysis within the TenetFolio interface.
- **No Monetization:** We do not sell, rent, or share your data. There are no third-party analytics, trackers, or "phone-home" telemetry scripts included in the source code.
- **Data Retention:** Data persists only on your local machine. If you delete the local database or the application, all cached data is removed.

## 4. Self-Hosted by Design

Because TenetFolio is entirely self-hosted:

- **No Account Creation:** There is no sign-up, login, or account registration with TenetFolio itself.
- **No Usage Analytics:** There are no analytics, tracking pixels, or telemetry of any kind.
- **No Dependency on TenetFolio Services:** The application functions entirely on your local machine with no reliance on infrastructure operated by the developer.

## 5. Open Source Transparency

As an open-source project, the source code for TenetFolio is available for public audit. Users are encouraged to review the code to verify that data handling matches the descriptions in this policy.

## 6. Contact

For questions regarding this policy, please open an issue on the TenetFolio GitHub repository.

To report security vulnerabilities, please follow the responsible disclosure process outlined in [SECURITY.md](SECURITY.md).
