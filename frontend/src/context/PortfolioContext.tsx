import { useState } from "react";
import { PortfolioContext } from "./context";
import type { PortfolioContextType } from "./context";

export interface PortfolioProviderProps {
  children: React.ReactNode;
}

export function PortfolioProvider({ children }: PortfolioProviderProps) {
  const [dashboardStale, setDashboardStale] = useState(false);

  const value: PortfolioContextType = {
    dashboardStale,
    setDashboardStale,
  };

  return (
    <PortfolioContext.Provider value={value}>
      {children}
    </PortfolioContext.Provider>
  );
}
