/**
 * Component to list and manage asset types
 */

import { useEffect, useState } from "react";
import { assetTypeApi } from "@/api";
import type { AssetType } from "@/types/assetType";
import { AssetTypeForm } from "./AssetTypeForm";

export function AssetTypeList() {
  const [assetTypes, setAssetTypes] = useState<AssetType[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editingType, setEditingType] = useState<AssetType | null>(null);

  const fetchAssetTypes = async () => {
    try {
      setLoading(true);
      const response = await assetTypeApi.list();
      setAssetTypes(response.data.items);
      setError(null);
    } catch (err) {
      setError("Failed to load asset types");
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAssetTypes();
  }, []);

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this asset type?")) {
      return;
    }

    try {
      await assetTypeApi.delete(id);
      await fetchAssetTypes();
    } catch (err) {
      const error = err as { response?: { data?: { detail?: string } } };
      alert(error.response?.data?.detail || "Failed to delete asset type");
    }
  };

  const handleAdd = () => {
    setEditingType(null);
    setShowForm(true);
  };

  const handleEdit = (type: AssetType) => {
    setEditingType(type);
    setShowForm(true);
  };

  const handleFormClose = () => {
    setShowForm(false);
    setEditingType(null);
    fetchAssetTypes();
  };

  if (loading) {
    return <div className="text-center py-8">Loading...</div>;
  }

  if (error) {
    return <div className="text-tf-negative p-4">{error}</div>;
  }

  return (
    <div className="max-w-2xl">
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-xl font-semibold">Asset Types</h2>
        <button
          onClick={handleAdd}
          className="px-4 py-2 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition"
        >
          + Add Type
        </button>
      </div>

      {assetTypes.length === 0 ? (
        <div className="text-center py-8 text-tf-text-tertiary">
          No asset types yet. Create one to get started.
        </div>
      ) : (
        <div className="space-y-3">
          {assetTypes.map((type) => (
            <div
              key={type.id}
              className="border border-tf-border-default rounded-lg p-4 flex items-center justify-between hover:border-tf-border-strong transition"
            >
              <div className="flex items-center gap-4">
                <div
                  className="w-6 h-6 rounded-full"
                  style={{ backgroundColor: type.color }}
                />
                <div>
                  <div className="font-medium">{type.name}</div>
                  <div className="text-sm text-tf-text-tertiary">
                    Target: {Number(type.target_percent).toFixed(2)}%
                  </div>
                </div>
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => handleEdit(type)}
                  className="px-3 py-1 text-sm text-tf-accent-primary hover:bg-tf-accent-muted rounded transition"
                >
                  Edit
                </button>
                <button
                  onClick={() => handleDelete(type.id)}
                  className="px-3 py-1 text-sm text-tf-negative hover:bg-tf-negative/10 rounded transition"
                >
                  Delete
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {showForm && (
        <AssetTypeForm
          assetType={editingType}
          onClose={handleFormClose}
        />
      )}
    </div>
  );
}
