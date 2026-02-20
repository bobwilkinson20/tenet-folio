import { describe, it, expect } from "vitest";
import { formatCurrency, formatCurrencyShort } from "@/utils/format";

describe("formatCurrency", () => {
  it("formats a positive number", () => {
    expect(formatCurrency(1234.56)).toBe("$1,234.56");
  });

  it("formats a numeric string", () => {
    expect(formatCurrency("1234.56")).toBe("$1,234.56");
  });

  it("returns dash for null", () => {
    expect(formatCurrency(null)).toBe("-");
  });

  it("returns dash for undefined", () => {
    expect(formatCurrency(undefined)).toBe("-");
  });

  it("returns dash for non-numeric string", () => {
    expect(formatCurrency("abc")).toBe("-");
  });

  it("formats zero", () => {
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("formats negative numbers", () => {
    expect(formatCurrency(-500)).toBe("-$500.00");
  });

  it("formats string zero", () => {
    expect(formatCurrency("0")).toBe("$0.00");
  });
});

describe("formatCurrencyShort", () => {
  it("formats millions", () => {
    expect(formatCurrencyShort(1_500_000)).toBe("$1.5M");
  });

  it("formats thousands", () => {
    expect(formatCurrencyShort(50_000)).toBe("$50k");
  });

  it("formats small values", () => {
    expect(formatCurrencyShort(500)).toBe("$500");
  });

  it("formats exactly one million", () => {
    expect(formatCurrencyShort(1_000_000)).toBe("$1.0M");
  });

  it("formats exactly one thousand", () => {
    expect(formatCurrencyShort(1_000)).toBe("$1k");
  });

  it("formats zero", () => {
    expect(formatCurrencyShort(0)).toBe("$0");
  });
});
