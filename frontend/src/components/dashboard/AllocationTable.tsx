/**
 * Table showing target vs actual allocation with variance
 */

import { useNavigate } from "react-router-dom";
import type { AllocationData } from "@/types/dashboard";

interface Props {
  allocations: AllocationData[];
  unassignedValue: string;
  allocationTotal: string;
}

export function AllocationTable({ allocations, unassignedValue, allocationTotal }: Props) {
  const navigate = useNavigate();
  const unassignedNum = parseFloat(unassignedValue);

  const getDeltaColor = (delta: number) => {
    if (Math.abs(delta) <= 2) return "text-tf-positive";
    if (Math.abs(delta) <= 5) return "text-tf-warning";
    return "text-tf-negative";
  };

  const getDeltaSymbol = (delta: number) => {
    if (delta > 0.01) return "↑";
    if (delta < -0.01) return "↓";
    return "—";
  };

  if (allocations.length === 0) {
    return (
      <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-lg p-6">
        <h2 className="text-xl font-semibold mb-4">Asset Allocation</h2>
        <div className="text-center py-8 text-tf-text-tertiary">
          Set up asset types and target allocation in Settings to see your allocation breakdown.
        </div>
      </div>
    );
  }

  return (
    <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-lg overflow-hidden">
      <div className="px-6 py-4 border-b border-tf-border-subtle">
        <h2 className="text-xl font-semibold">Asset Allocation</h2>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-tf-bg-surface">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                Type
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                Target
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                Actual
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                Delta
              </th>
              <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                Value
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-tf-border-subtle">
            {allocations.map((alloc) => {
              const delta = parseFloat(alloc.delta_percent);
              return (
                <tr
                  key={alloc.asset_type_id}
                  className="hover:bg-tf-bg-elevated cursor-pointer"
                  onClick={() => navigate(`/asset-types/${alloc.asset_type_id}`)}
                >
                  <td className="px-6 py-4 whitespace-nowrap">
                    <div className="flex items-center gap-3">
                      <div
                        className="w-4 h-4 rounded-full"
                        style={{ backgroundColor: alloc.asset_type_color }}
                      />
                      <span className="text-sm font-medium text-tf-text-primary">
                        {alloc.asset_type_name}
                      </span>
                    </div>
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
                    {parseFloat(alloc.target_percent).toFixed(1)}%
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
                    {parseFloat(alloc.actual_percent).toFixed(1)}%
                  </td>
                  <td
                    className={`px-6 py-4 whitespace-nowrap text-right text-sm font-medium ${getDeltaColor(
                      delta
                    )}`}
                  >
                    {delta > 0 ? "+" : ""}
                    {delta.toFixed(1)}% {getDeltaSymbol(delta)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
                    ${parseFloat(alloc.value).toLocaleString(undefined, {
                      minimumFractionDigits: 2,
                      maximumFractionDigits: 2,
                    })}
                  </td>
                </tr>
              );
            })}
            {unassignedNum > 0 && (
              <tr
                className="bg-tf-warning/10 cursor-pointer hover:bg-tf-warning/15"
                onClick={() => navigate("/asset-types/unassigned")}
              >
                <td className="px-6 py-4 whitespace-nowrap">
                  <div className="flex items-center gap-3">
                    <div className="w-4 h-4 rounded-full bg-tf-text-tertiary" />
                    <span className="text-sm font-medium text-tf-text-secondary">
                      Unknown
                    </span>
                  </div>
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-secondary">
                  —
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-secondary">
                  —
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-secondary">
                  —
                </td>
                <td className="px-6 py-4 whitespace-nowrap text-right text-sm text-tf-text-primary">
                  ${unassignedNum.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}
                </td>
              </tr>
            )}
          </tbody>
          <tfoot>
            <tr className="bg-tf-bg-surface border-t border-tf-border-default font-semibold">
              <td className="px-6 py-3 whitespace-nowrap text-sm text-tf-text-primary">
                Total
              </td>
              <td className="px-6 py-3 whitespace-nowrap text-right text-sm text-tf-text-primary">
                —
              </td>
              <td className="px-6 py-3 whitespace-nowrap text-right text-sm text-tf-text-primary">
                —
              </td>
              <td className="px-6 py-3 whitespace-nowrap text-right text-sm text-tf-text-primary">
                —
              </td>
              <td className="px-6 py-3 whitespace-nowrap text-right text-sm text-tf-text-primary">
                ${parseFloat(allocationTotal).toLocaleString(undefined, {
                  minimumFractionDigits: 2,
                  maximumFractionDigits: 2,
                })}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>

      <div className="px-6 py-3 bg-tf-bg-surface border-t border-tf-border-subtle text-sm text-tf-text-secondary">
        <div className="flex justify-end gap-4">
          <span>
            <span className="text-tf-positive">Green</span>: Within ±2%
          </span>
          <span>
            <span className="text-tf-warning">Yellow</span>: Within ±5%
          </span>
          <span>
            <span className="text-tf-negative">Red</span>: Exceeds ±5%
          </span>
        </div>
      </div>
    </div>
  );
}
