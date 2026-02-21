import { describe, it, expect } from "vitest";
import {
  isSyntheticTicker,
  isCashTicker,
  ZERO_BALANCE_TICKER,
} from "@/utils/ticker";

describe("ticker utilities", () => {
  describe("isSyntheticTicker", () => {
    it("returns true for _SF: prefixed tickers", () => {
      expect(isSyntheticTicker("_SF:abc12345")).toBe(true);
      expect(isSyntheticTicker("_SF:12345678")).toBe(true);
    });

    it("returns true for _MAN: prefixed tickers", () => {
      expect(isSyntheticTicker("_MAN:abc123456789")).toBe(true);
      expect(isSyntheticTicker("_MAN:123456789012")).toBe(true);
    });

    it("returns true for _PLAID: prefixed tickers", () => {
      expect(isSyntheticTicker("_PLAID:abc12345")).toBe(true);
      expect(isSyntheticTicker("_PLAID:12345678")).toBe(true);
    });

    it("returns false for regular tickers", () => {
      expect(isSyntheticTicker("AAPL")).toBe(false);
      expect(isSyntheticTicker("VTI")).toBe(false);
      expect(isSyntheticTicker("BRK.B")).toBe(false);
    });

    it("returns false for cash tickers", () => {
      expect(isSyntheticTicker("_CASH:USD")).toBe(false);
      expect(isSyntheticTicker("_CASH:EUR")).toBe(false);
    });

    it("returns true for _ZERO_BALANCE ticker", () => {
      expect(isSyntheticTicker(ZERO_BALANCE_TICKER)).toBe(true);
      expect(isSyntheticTicker("_ZERO_BALANCE")).toBe(true);
    });

    it("returns false for empty string", () => {
      expect(isSyntheticTicker("")).toBe(false);
    });
  });

  describe("isCashTicker", () => {
    it("returns true for _CASH: prefixed tickers", () => {
      expect(isCashTicker("_CASH:USD")).toBe(true);
      expect(isCashTicker("_CASH:EUR")).toBe(true);
      expect(isCashTicker("_CASH:GBP")).toBe(true);
    });

    it("returns false for regular tickers", () => {
      expect(isCashTicker("AAPL")).toBe(false);
      expect(isCashTicker("VTI")).toBe(false);
    });

    it("returns false for synthetic tickers", () => {
      expect(isCashTicker("_SF:abc12345")).toBe(false);
      expect(isCashTicker("_MAN:abc123456789")).toBe(false);
    });

    it("returns false for empty string", () => {
      expect(isCashTicker("")).toBe(false);
    });
  });
});
