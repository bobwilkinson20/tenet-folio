/**
 * Tests for PortfolioContext - specifically the dashboardStale state
 */

import { describe, it, expect } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { PortfolioProvider, usePortfolioContext } from "@/context";

function TestComponent() {
  const { dashboardStale, setDashboardStale } = usePortfolioContext();

  return (
    <div>
      <span data-testid="stale-status">{dashboardStale ? "stale" : "fresh"}</span>
      <button onClick={() => setDashboardStale(true)}>Mark Stale</button>
      <button onClick={() => setDashboardStale(false)}>Mark Fresh</button>
    </div>
  );
}

describe("PortfolioContext - dashboardStale", () => {
  it("should initialize dashboardStale as false", () => {
    render(
      <PortfolioProvider>
        <TestComponent />
      </PortfolioProvider>
    );

    expect(screen.getByTestId("stale-status")).toHaveTextContent("fresh");
  });

  it("should update dashboardStale to true when setDashboardStale(true) is called", () => {
    render(
      <PortfolioProvider>
        <TestComponent />
      </PortfolioProvider>
    );

    act(() => {
      screen.getByText("Mark Stale").click();
    });

    expect(screen.getByTestId("stale-status")).toHaveTextContent("stale");
  });

  it("should update dashboardStale back to false when setDashboardStale(false) is called", () => {
    render(
      <PortfolioProvider>
        <TestComponent />
      </PortfolioProvider>
    );

    // First mark as stale
    act(() => {
      screen.getByText("Mark Stale").click();
    });
    expect(screen.getByTestId("stale-status")).toHaveTextContent("stale");

    // Then mark as fresh
    act(() => {
      screen.getByText("Mark Fresh").click();
    });
    expect(screen.getByTestId("stale-status")).toHaveTextContent("fresh");
  });
});
