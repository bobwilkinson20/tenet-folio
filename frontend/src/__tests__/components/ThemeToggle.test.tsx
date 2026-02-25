import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ThemeToggle } from "@/components/layout/ThemeToggle";

const mockSetTheme = vi.fn();
let mockTheme = "system" as "system" | "light" | "dark";

vi.mock("@/hooks/useTheme", () => ({
  useTheme: () => ({
    theme: mockTheme,
    resolvedTheme: mockTheme === "system" ? "dark" : mockTheme,
    setTheme: mockSetTheme,
    loading: false,
  }),
}));

describe("ThemeToggle", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockTheme = "system";
  });

  it("renders a button with action-oriented aria-label", () => {
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Switch to light theme" })).toBeInTheDocument();
  });

  it("shows correct aria-label for light mode", () => {
    mockTheme = "light";
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("shows correct aria-label for dark mode", () => {
    mockTheme = "dark";
    render(<ThemeToggle />);
    expect(screen.getByRole("button", { name: "Switch to system theme" })).toBeInTheDocument();
  });

  it("cycles from system to light on click", async () => {
    mockTheme = "system";
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole("button"));
    expect(mockSetTheme).toHaveBeenCalledWith("light");
  });

  it("cycles from light to dark on click", async () => {
    mockTheme = "light";
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole("button"));
    expect(mockSetTheme).toHaveBeenCalledWith("dark");
  });

  it("cycles from dark to system on click", async () => {
    mockTheme = "dark";
    render(<ThemeToggle />);

    await userEvent.click(screen.getByRole("button"));
    expect(mockSetTheme).toHaveBeenCalledWith("system");
  });
});
