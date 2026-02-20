import { describe, it, expect } from "vitest";
import { extractApiErrorMessage } from "@/utils/errors";

describe("extractApiErrorMessage", () => {
  it("extracts detail from axios-shaped error", () => {
    const err = { response: { data: { detail: "Name already exists" } } };
    expect(extractApiErrorMessage(err)).toBe("Name already exists");
  });

  it("falls back to Error.message when no response detail", () => {
    const err = new Error("Network Error");
    expect(extractApiErrorMessage(err)).toBe("Network Error");
  });

  it("uses default fallback for unknown error shape", () => {
    expect(extractApiErrorMessage("something")).toBe("An unexpected error occurred");
  });

  it("uses custom fallback when provided", () => {
    expect(extractApiErrorMessage({}, "Custom fallback")).toBe("Custom fallback");
  });

  it("handles null error", () => {
    expect(extractApiErrorMessage(null)).toBe("An unexpected error occurred");
  });

  it("handles undefined error", () => {
    expect(extractApiErrorMessage(undefined)).toBe("An unexpected error occurred");
  });

  it("prefers response detail over Error.message", () => {
    const err = Object.assign(new Error("generic"), {
      response: { data: { detail: "Specific API error" } },
    });
    expect(extractApiErrorMessage(err)).toBe("Specific API error");
  });
});
