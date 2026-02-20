/**
 * Settings page with tabs for Asset Types, Securities, and Portfolio allocation
 */

import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { AssetTypeList } from "@/components/settings/AssetTypeList";
import { ProviderList } from "@/components/settings/ProviderList";
import { SecurityList } from "@/components/settings/SecurityList";
import { TargetAllocationForm } from "@/components/settings/TargetAllocationForm";

type TabValue = "providers" | "types" | "securities" | "portfolio";

export function Settings() {
  const [searchParams] = useSearchParams();

  // Initialize tab from query params
  const initialTab = (() => {
    const tab = searchParams.get("tab");
    if (tab === "providers" || tab === "securities" || tab === "portfolio" || tab === "types") {
      return tab;
    }
    return "providers" as TabValue;
  })();

  const [activeTab, setActiveTab] = useState<TabValue>(initialTab);

  return (
    <div className="p-6 w-full max-w-5xl">
      <h1 className="text-3xl font-bold mb-6">Settings</h1>

      {/* Tab Navigation */}
      <div className="border-b border-tf-border-default mb-6">
        <nav className="flex -mb-px space-x-8">
          <button
            onClick={() => setActiveTab("providers")}
            className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "providers"
                ? "border-tf-accent-primary text-tf-accent-primary"
                : "border-transparent text-tf-text-tertiary hover:text-tf-text-primary hover:border-tf-border-strong"
            }`}
          >
            Providers
          </button>
          <button
            onClick={() => setActiveTab("types")}
            className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "types"
                ? "border-tf-accent-primary text-tf-accent-primary"
                : "border-transparent text-tf-text-tertiary hover:text-tf-text-primary hover:border-tf-border-strong"
            }`}
          >
            Asset Types
          </button>
          <button
            onClick={() => setActiveTab("portfolio")}
            className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "portfolio"
                ? "border-tf-accent-primary text-tf-accent-primary"
                : "border-transparent text-tf-text-tertiary hover:text-tf-text-primary hover:border-tf-border-strong"
            }`}
          >
            Portfolio
          </button>
          <button
            onClick={() => setActiveTab("securities")}
            className={`py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "securities"
                ? "border-tf-accent-primary text-tf-accent-primary"
                : "border-transparent text-tf-text-tertiary hover:text-tf-text-primary hover:border-tf-border-strong"
            }`}
          >
            Securities
          </button>
        </nav>
      </div>

      {/* Tab Content */}
      <div>
        {activeTab === "providers" && <ProviderList />}
        {activeTab === "types" && <AssetTypeList />}
        {activeTab === "portfolio" && <TargetAllocationForm />}
        {activeTab === "securities" && <SecurityList />}
      </div>
    </div>
  );
}
