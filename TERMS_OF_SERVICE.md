# Terms of Service

**TenetFolio — Sovereign Financial Architecture**

*Last updated: February 21, 2026*

---

## 1. Acceptance of Terms

By accessing, downloading, installing, or using TenetFolio ("the Software"), you agree to be bound by these Terms of Service ("Terms"). If you do not agree to these Terms, do not use the Software.

TenetFolio is open-source software distributed under the [MIT License](LICENSE), which governs your rights to use, copy, modify, and distribute the code. These Terms provide additional context regarding disclaimers, third-party integrations, and limitations of liability. In the event of any conflict between these Terms and the MIT License, the MIT License shall prevail with respect to your rights to the source code.

## 2. Description of the Service

TenetFolio is a personal portfolio tracking application that connects to brokerage accounts through third-party data providers — including SnapTrade, SimpleFIN, Interactive Brokers, Coinbase, and Charles Schwab — to display holdings, track asset allocation, and monitor net worth over time. Market data and pricing information are retrieved on a best-effort basis from publicly available sources, including Yahoo Finance and CoinGecko. The accuracy, availability, and timeliness of this data are not guaranteed.

TenetFolio is designed to be self-hosted. Users are responsible for deploying, configuring, and maintaining their own instances of the Software, including the management of API credentials, database storage, and server infrastructure.

## 3. Not Financial Advice

**TenetFolio is an informational tool only.** Nothing in the Software or its documentation constitutes financial, investment, tax, or legal advice. TenetFolio does not recommend, endorse, or suggest any investment strategy, security, or financial product.

You acknowledge that:

- TenetFolio is not a registered broker-dealer, investment adviser, or financial planner.
- All portfolio data, valuations, performance metrics, and allocation breakdowns displayed by TenetFolio are for informational and educational purposes only.
- You are solely responsible for your own investment decisions and should consult a qualified financial professional before making any financial decisions.
- Data displayed by TenetFolio may be delayed, incomplete, or inaccurate due to factors outside our control, including third-party API limitations, market data delays, and synchronization timing.

## 4. User Responsibilities

As a user of TenetFolio, you agree to:

- **Secure your own instance.** You are responsible for the security of your deployment environment, including server access controls, database encryption, network configuration, and API credential storage.
- **Manage your own credentials.** TenetFolio connects to third-party brokerage and data providers using credentials and API keys that you supply. You are responsible for safeguarding these credentials and complying with each provider's terms of service.
- **Use the Software lawfully.** You will not use TenetFolio for any purpose that violates applicable local, state, national, or international laws or regulations.
- **Maintain accurate configuration.** You are responsible for ensuring that your provider integrations, account mappings, and application settings are correctly configured.

## 5. Third-Party Services and Integrations

TenetFolio integrates with third-party services to retrieve brokerage account data and market information. These third-party services include, but are not limited to:

- **SnapTrade** — brokerage account linking and data retrieval
- **Plaid** — financial account aggregation
- **SimpleFIN** — financial account aggregation
- **Interactive Brokers** — Flex Web Service for account data
- **Coinbase** — cryptocurrency account data via the Advanced Trade API
- **Charles Schwab** — brokerage account data via the Schwab Developer API
- **Yahoo Finance** — market data and pricing, retrieved on a best-effort basis from publicly available sources (not an official API integration)
- **CoinGecko** — cryptocurrency market data, retrieved on a best-effort basis

You acknowledge and agree that:

- Each third-party service is governed by its own terms of service, privacy policy, and usage restrictions. You are responsible for reviewing and complying with those terms independently.
- TenetFolio is not affiliated with, endorsed by, or sponsored by any of the above third-party providers unless explicitly stated otherwise.
- TenetFolio does not control the availability, accuracy, completeness, or timeliness of data provided by third-party services. We are not responsible for any errors, outages, rate-limiting, API changes, or data discrepancies originating from these services.
- Third-party providers may modify, restrict, or discontinue their APIs or services at any time, which may affect TenetFolio's functionality. We will make reasonable efforts to adapt to such changes but cannot guarantee uninterrupted service.

## 6. Data and Privacy

TenetFolio is designed with a privacy-first, self-hosted architecture. Please refer to our [Privacy Policy](PRIVACY.md) for detailed information about data handling practices.

In summary:

- **Your data stays with you.** Financial data retrieved by TenetFolio is stored in your local database on your own infrastructure. TenetFolio does not transmit your portfolio data to any central server operated by the TenetFolio project.
- **Credential storage.** API keys and authentication tokens are stored using your system's secure credential storage (macOS Keychain where available, with `.env` file fallback). You are responsible for protecting access to these credentials.
- **No telemetry.** TenetFolio does not collect analytics, usage telemetry, or personally identifiable information from your self-hosted instance.

## 7. Intellectual Property

TenetFolio is released under the [MIT License](LICENSE). Subject to the terms of that license, you are free to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software.

All trademarks, service marks, and trade names of third-party brokerage providers, data services, and other companies referenced in the Software or its documentation are the property of their respective owners.

## 8. Disclaimer of Warranties

**THE SOFTWARE IS PROVIDED "AS IS" AND "AS AVAILABLE," WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED.** To the fullest extent permitted by applicable law, TenetFolio disclaims all warranties, including but not limited to:

- Implied warranties of merchantability, fitness for a particular purpose, and non-infringement.
- Any warranty that the Software will be uninterrupted, error-free, secure, or free of viruses or other harmful components.
- Any warranty regarding the accuracy, reliability, or completeness of any data retrieved through the Software, including portfolio valuations, market prices, account balances, and performance calculations.

You expressly acknowledge that financial data displayed by TenetFolio may contain errors or inaccuracies and should not be relied upon as the sole basis for any financial decision.

## 9. Limitation of Liability

**TO THE MAXIMUM EXTENT PERMITTED BY APPLICABLE LAW, IN NO EVENT SHALL THE TENETFOLIO PROJECT, ITS CONTRIBUTORS, OR ITS MAINTAINERS BE LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR PUNITIVE DAMAGES**, including but not limited to:

- Loss of profits, revenue, data, or financial losses.
- Damages arising from reliance on data displayed by the Software.
- Damages arising from unauthorized access to your deployment or credentials.
- Damages arising from interruptions or failures of third-party services.
- Damages arising from errors in portfolio valuations, market data, or synchronization.

This limitation applies regardless of the legal theory under which liability is asserted, whether in contract, tort (including negligence), strict liability, or otherwise, even if TenetFolio has been advised of the possibility of such damages.

## 10. Account Termination and Data Deletion

Since TenetFolio is self-hosted, you maintain full control over your data and your instance at all times.

- **Discontinuing use.** You may stop using TenetFolio at any time by shutting down your instance and deleting your local database and configuration files.
- **Revoking provider access.** To fully disconnect from third-party providers, you should revoke API keys and access tokens directly through each provider's platform (e.g., SnapTrade dashboard, Coinbase developer portal, Schwab developer portal).
- **Data deletion.** All data stored by TenetFolio resides on your infrastructure. Deleting the database file and any credential storage entries will permanently remove all data associated with your instance.

## 11. Modifications to These Terms

We reserve the right to update or modify these Terms at any time. Changes will be reflected by updating the "Last updated" date at the top of this document and by committing the revised Terms to the project repository.

Your continued use of the Software after any changes to these Terms constitutes your acceptance of the revised Terms. We encourage you to review these Terms periodically.

## 12. Open Source Contributions

Contributions to TenetFolio are governed by the [Contributing Guidelines](CONTRIBUTING.md) and the [Code of Conduct](CODE_OF_CONDUCT.md). By submitting a contribution (including pull requests, issues, or documentation), you agree that your contribution will be licensed under the same MIT License that covers the project.

## 13. Governing Law

These Terms shall be governed by and construed in accordance with the laws of the State of Washington, United States, without regard to conflict of law principles. Any disputes arising under these Terms shall be resolved in the state or federal courts located in the State of Washington.

## 14. Severability

If any provision of these Terms is found to be unenforceable or invalid, that provision shall be limited or eliminated to the minimum extent necessary, and the remaining provisions shall remain in full force and effect.

## 15. Entire Agreement

These Terms, together with the [Privacy Policy](PRIVACY.md), [Security Policy](SECURITY.md), and [MIT License](LICENSE), constitute the entire agreement between you and the TenetFolio project regarding your use of the Software.

## 16. Contact

For questions about these Terms, please open an issue on the [TenetFolio GitHub repository](https://github.com/bobwilkinson20/tenet-folio) or reach out to the project maintainers.

---

*TenetFolio is an open-source project and is not affiliated with any brokerage, financial institution, or data provider.*
