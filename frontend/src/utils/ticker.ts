/**
 * Utility functions for handling ticker symbols.
 */

export const ZERO_BALANCE_TICKER = "_ZERO_BALANCE";

/**
 * Checks if a ticker is a synthetic internal identifier.
 * Synthetic tickers include:
 * - _SF:{hash} - SimpleFIN provider for non-tradable holdings
 * - _MAN:{hash} - Manual holdings for "Other" assets
 * - _ZERO_BALANCE - Sentinel for accounts with zero holdings
 *
 * These should generally be hidden from users in UI views.
 */
export function isSyntheticTicker(ticker: string): boolean {
  return (
    ticker.startsWith("_SF:") ||
    ticker.startsWith("_MAN:") ||
    ticker === ZERO_BALANCE_TICKER
  );
}

/**
 * Checks if a ticker represents a cash position.
 * Cash tickers use the format _CASH:{currency_code}
 */
export function isCashTicker(ticker: string): boolean {
  return ticker.startsWith("_CASH:");
}
