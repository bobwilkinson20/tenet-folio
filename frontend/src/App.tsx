import { BrowserRouter, Routes, Route } from "react-router-dom";
import { PortfolioProvider } from "./context";
import { Layout } from "./components/layout/Layout";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { DashboardPage } from "./pages/Dashboard";
import { AccountsPage } from "./pages/Accounts";
import { AccountDetailsPage } from "./pages/AccountDetails";
import { AssetTypeDetailsPage } from "./pages/AssetTypeDetails";
import { Settings } from "./pages/Settings";
import { RealizedGainsPage } from "./pages/RealizedGains";
import { ReturnsPage } from "./pages/Returns";
import { CashFlowReviewPage } from "./pages/CashFlowReview";

export default function App() {
  return (
    <BrowserRouter>
      <PortfolioProvider>
        <Layout>
          <ErrorBoundary>
            <Routes>
              <Route path="/" element={<DashboardPage />} />
              <Route path="/accounts" element={<AccountsPage />} />
              <Route path="/accounts/:id" element={<AccountDetailsPage />} />
              <Route path="/asset-types/:id" element={<AssetTypeDetailsPage />} />
              <Route path="/realized-gains" element={<RealizedGainsPage />} />
              <Route path="/returns" element={<ReturnsPage />} />
              <Route path="/cashflows" element={<CashFlowReviewPage />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </ErrorBoundary>
        </Layout>
      </PortfolioProvider>
    </BrowserRouter>
  );
}
