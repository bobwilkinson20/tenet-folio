/**
 * Component to list securities and assign asset types
 */

import { useEffect, useState } from "react";
import { assetTypeApi, securitiesApi } from "@/api";
import type { AssetType, SecurityWithType } from "@/types/assetType";
import { AssetTypeSelect } from "@/components/common/AssetTypeSelect";
import { extractApiErrorMessage } from "@/utils/errors";

export function SecurityList() {
  const [securities, setSecurities] = useState<SecurityWithType[]>([]);
  const [assetTypes, setAssetTypes] = useState<AssetType[]>([]);
  const [search, setSearch] = useState("");
  const [unassignedOnly, setUnassignedOnly] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [securitiesResponse, typesResponse] = await Promise.all([
        securitiesApi.list({ search, unassigned_only: unassignedOnly }),
        assetTypeApi.list(),
      ]);
      setSecurities(securitiesResponse.data);
      setAssetTypes(typesResponse.data.items);
      setError(null);
    } catch (err) {
      setError("Failed to load securities");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search, unassignedOnly]);

  const handleTypeChange = async (securityId: string, assetTypeId: string | null) => {
    try {
      await securitiesApi.updateType(securityId, assetTypeId);
      await fetchData();
    } catch (err) {
      alert(extractApiErrorMessage(err, "Failed to update security"));
    }
  };

  const unassignedCount = securities.filter((s) => !s.asset_type_id).length;

  if (loading) {
    return <div className="text-center py-8">Loading...</div>;
  }

  if (error) {
    return <div className="text-tf-negative p-4">{error}</div>;
  }

  return (
    <div>
      <div className="mb-6 space-y-4">
        <div>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="🔍 Search by ticker or name"
            className="w-full px-4 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
          />
        </div>

        <div className="flex items-center gap-2">
          <input
            type="checkbox"
            id="unassigned"
            checked={unassignedOnly}
            onChange={(e) => setUnassignedOnly(e.target.checked)}
            className="w-4 h-4"
          />
          <label htmlFor="unassigned" className="text-sm">
            Show unassigned only
          </label>
        </div>

        {unassignedCount > 0 && (
          <div className="bg-tf-warning/10 border border-tf-warning/20 text-tf-warning px-4 py-3 rounded">
            ⚠ {unassignedCount} securities need type assignment
          </div>
        )}
      </div>

      {securities.length === 0 ? (
        <div className="text-center py-8 text-tf-text-tertiary">
          {unassignedOnly
            ? "No unassigned securities"
            : "No securities found. Sync your accounts to populate securities."}
        </div>
      ) : (
        <div className="border border-tf-border-default rounded-lg overflow-hidden">
          <table className="w-full">
            <thead className="bg-tf-bg-surface">
              <tr>
                <th className="px-4 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                  Ticker
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                  Name
                </th>
                <th className="px-4 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase tracking-wider">
                  Asset Type
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-tf-border-subtle">
              {securities.map((security) => (
                <tr key={security.id} className="hover:bg-tf-bg-elevated">
                  <td className="px-4 py-3 text-sm font-medium text-tf-text-primary">
                    {security.ticker}
                  </td>
                  <td className="px-4 py-3 text-sm text-tf-text-tertiary">
                    {security.name || "—"}
                  </td>
                  <td className="px-4 py-3 text-sm">
                    <AssetTypeSelect
                      value={security.asset_type_id}
                      onChange={(value) => handleTypeChange(security.id, value)}
                      assetTypes={assetTypes}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
