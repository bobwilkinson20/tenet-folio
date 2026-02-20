import { useContext } from "react";
import { PortfolioContext } from "./context";

export function usePortfolioContext() {
  const context = useContext(PortfolioContext);
  if (!context) {
    throw new Error("usePortfolioContext must be used within PortfolioProvider");
  }
  return context;
}
