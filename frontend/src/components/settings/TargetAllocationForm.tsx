/**
 * Form for setting target allocation percentages
 */

import { useEffect, useState } from "react";
import { assetTypeApi, portfolioApi } from "@/api";
import type { AssetType } from "@/types/assetType";
import { usePortfolioContext } from "@/context";
import { extractApiErrorMessage } from "@/utils/errors";

export function TargetAllocationForm() {
  const { setDashboardStale } = usePortfolioContext();
  const [assetTypes, setAssetTypes] = useState<AssetType[]>([]);
  const [targets, setTargets] = useState<Record<string, number>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [typesResponse, allocationResponse] = await Promise.all([
        assetTypeApi.list(),
        portfolioApi.getAllocation(),
      ]);

      setAssetTypes(typesResponse.data.items);

      // Build targets map
      const targetsMap: Record<string, number> = {};
      allocationResponse.data.allocations.forEach((alloc) => {
        targetsMap[alloc.asset_type_id] = Number(alloc.target_percent);
      });
      setTargets(targetsMap);
      setError(null);
    } catch (err) {
      setError("Failed to load allocation data");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleTargetChange = (assetTypeId: string, value: string) => {
    const numValue = parseFloat(value) || 0;
    setTargets((prev) => ({
      ...prev,
      [assetTypeId]: numValue,
    }));
    setSuccess(false);
  };

  const calculateTotal = () => {
    return Object.values(targets).reduce((sum, val) => sum + val, 0);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const total = calculateTotal();
    if (Math.abs(total - 100) > 0.01) {
      setError(`Target allocations must sum to 100%, currently ${total.toFixed(2)}%`);
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      const allocations = assetTypes.map((type) => ({
        asset_type_id: type.id,
        target_percent: targets[type.id] || 0,
      }));

      await portfolioApi.updateAllocation(allocations);
      setDashboardStale(true);
      setSuccess(true);
      setTimeout(() => setSuccess(false), 3000);
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to save allocation"));
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) {
    return <div className="text-center py-8">Loading...</div>;
  }

  if (assetTypes.length === 0) {
    return (
      <div className="text-center py-8 text-tf-text-tertiary">
        No asset types yet. Create asset types first in the Asset Types tab.
      </div>
    );
  }

  const total = calculateTotal();
  const isValid = Math.abs(total - 100) < 0.01;

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h2 className="text-xl font-semibold mb-2">Target Allocation</h2>
        <p className="text-tf-text-secondary text-sm">
          Define your target asset allocation. Percentages must sum to exactly
          100%.
        </p>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="space-y-4 mb-6">
          {assetTypes.map((type) => (
            <div
              key={type.id}
              className="border border-tf-border-default rounded-lg p-4 flex items-center justify-between"
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-6 h-6 rounded-full"
                  style={{ backgroundColor: type.color }}
                />
                <span className="font-medium">{type.name}</span>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="number"
                  min="0"
                  max="100"
                  step="0.01"
                  value={targets[type.id] || 0}
                  onChange={(e) => handleTargetChange(type.id, e.target.value)}
                  className="w-24 px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary text-right"
                  disabled={submitting}
                />
                <span className="text-tf-text-secondary">%</span>
              </div>
            </div>
          ))}
        </div>

        <div className="border-t border-tf-border-default pt-4 mb-6">
          <div className="flex items-center justify-between text-lg font-semibold">
            <span>Total:</span>
            <div className="flex items-center gap-2">
              <span className={isValid ? "text-tf-positive" : "text-tf-negative"}>
                {total.toFixed(2)}%
              </span>
              {isValid ? (
                <span className="text-tf-positive">✓</span>
              ) : (
                <span className="text-tf-negative">✗</span>
              )}
            </div>
          </div>
          {!isValid && (
            <div className="mt-2 text-sm text-tf-negative">
              ⚠ Target allocation must sum to exactly 100%
            </div>
          )}
        </div>

        {error && (
          <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm">
            {error}
          </div>
        )}

        {success && (
          <div className="mb-4 p-3 bg-tf-positive/10 border border-tf-positive/20 text-tf-positive rounded text-sm">
            ✓ Allocation saved successfully
          </div>
        )}

        <button
          type="submit"
          disabled={!isValid || submitting}
          className="px-6 py-2 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {submitting ? "Saving..." : "Save"}
        </button>
      </form>
    </div>
  );
}
