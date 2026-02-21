import { useCallback, useEffect, useState } from "react";
import { plaidApi } from "@/api/plaid";
import type { PlaidItem } from "@/api/plaid";
import { PlaidLinkButton } from "./PlaidLinkButton";

export function PlaidItemList() {
  const [items, setItems] = useState<PlaidItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [removingId, setRemovingId] = useState<string | null>(null);
  const [fetchError, setFetchError] = useState(false);
  const [removeError, setRemoveError] = useState<string | null>(null);

  const fetchItems = useCallback(async () => {
    try {
      setLoading(true);
      setFetchError(false);
      const response = await plaidApi.listItems();
      setItems(response.data);
    } catch {
      setFetchError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchItems();
  }, [fetchItems]);

  const handleRemove = async (itemId: string) => {
    setRemovingId(itemId);
    setRemoveError(null);
    try {
      await plaidApi.removeItem(itemId);
      setItems((prev) => prev.filter((i) => i.item_id !== itemId));
    } catch {
      setRemoveError("Failed to remove institution. Please try again.");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="mt-3 space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium text-tf-text-secondary">
          Linked Institutions
        </span>
        <PlaidLinkButton onSuccess={fetchItems} />
      </div>

      {removeError && (
        <p className="text-xs text-tf-negative">{removeError}</p>
      )}

      {fetchError ? (
        <p className="text-xs text-tf-negative">
          Failed to load linked institutions.
        </p>
      ) : loading && items.length === 0 ? (
        <p className="text-xs text-tf-text-tertiary">Loading...</p>
      ) : items.length === 0 ? (
        <p className="text-xs text-tf-text-tertiary">
          No institutions linked yet. Click "Link Institution" to get started.
        </p>
      ) : (
        <ul className="space-y-2">
          {items.map((item) => (
            <li
              key={item.item_id}
              className="flex items-center justify-between rounded border border-tf-border-default px-3 py-2 text-sm"
            >
              <span className="text-tf-text-primary">
                {item.institution_name || item.item_id}
              </span>
              <button
                onClick={() => handleRemove(item.item_id)}
                disabled={removingId === item.item_id}
                className="text-xs text-tf-negative hover:underline disabled:opacity-50"
              >
                {removingId === item.item_id ? "Removing..." : "Remove"}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
