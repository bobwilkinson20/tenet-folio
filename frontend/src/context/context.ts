import { createContext } from "react";

export interface PortfolioContextType {
  dashboardStale: boolean;
  setDashboardStale: (stale: boolean) => void;
}

export const PortfolioContext = createContext<PortfolioContextType | undefined>(
  undefined
);
