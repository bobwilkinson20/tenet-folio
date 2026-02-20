/**
 * Modal form for creating/editing asset types
 */

import { useEffect, useRef, useState } from "react";
import { HexColorPicker } from "react-colorful";
import { assetTypeApi } from "@/api";
import type { AssetType } from "@/types/assetType";
import { DEFAULT_COLORS, isDefaultColor } from "@/types/assetType";
import { extractApiErrorMessage } from "@/utils/errors";
import { Modal } from "@/components/common/Modal";

interface Props {
  assetType: AssetType | null;
  onClose: () => void;
}

export function AssetTypeForm({ assetType, onClose }: Props) {
  const [name, setName] = useState("");
  const [color, setColor] = useState(DEFAULT_COLORS[0]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showColorPicker, setShowColorPicker] = useState(false);
  const colorPickerRef = useRef<HTMLDivElement>(null);

  const isCustom = !isDefaultColor(color);

  // Close color picker when clicking outside
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (
        colorPickerRef.current &&
        !colorPickerRef.current.contains(event.target as Node)
      ) {
        setShowColorPicker(false);
      }
    }

    if (showColorPicker) {
      document.addEventListener("mousedown", handleClickOutside);
      return () => document.removeEventListener("mousedown", handleClickOutside);
    }
  }, [showColorPicker]);

  useEffect(() => {
    if (assetType) {
      setName(assetType.name);
      setColor(assetType.color);
    }
  }, [assetType]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    if (!name.trim()) {
      setError("Name is required");
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      if (assetType) {
        // Update existing
        await assetTypeApi.update(assetType.id, { name, color });
      } else {
        // Create new
        await assetTypeApi.create({ name, color });
      }

      onClose();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Failed to save asset type"));
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Modal isOpen={true} onClose={onClose}>
        <h3 className="text-lg font-semibold mb-4">
          {assetType ? "Edit Asset Type" : "Add Asset Type"}
        </h3>

        <form onSubmit={handleSubmit}>
          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full px-3 py-2 bg-tf-bg-surface border border-tf-border-default rounded text-tf-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary"
              placeholder="e.g., US Equities"
              disabled={submitting}
            />
          </div>

          <div className="mb-4">
            <label className="block text-sm font-medium text-tf-text-secondary mb-2">
              Color
            </label>
            <div className="flex gap-2 flex-wrap">
              {DEFAULT_COLORS.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => {
                    setColor(c);
                    setShowColorPicker(false);
                  }}
                  className={`w-10 h-10 rounded transition ${
                    color === c ? "ring-2 ring-tf-accent-primary ring-offset-2" : ""
                  }`}
                  style={{ backgroundColor: c }}
                  disabled={submitting}
                />
              ))}
              <div className="relative" ref={colorPickerRef}>
                <button
                  type="button"
                  onClick={() => setShowColorPicker(!showColorPicker)}
                  aria-label="Custom color"
                  className={`w-10 h-10 rounded transition ${
                    isCustom ? "ring-2 ring-tf-accent-primary ring-offset-2" : ""
                  }`}
                  style={{
                    background: isCustom
                      ? color
                      : "conic-gradient(red, yellow, lime, aqua, blue, magenta, red)",
                  }}
                  disabled={submitting}
                />
                {showColorPicker && (
                  <div className="absolute top-12 left-0 z-10 bg-tf-bg-surface p-3 rounded-lg border border-tf-border-default">
                    <HexColorPicker color={color} onChange={setColor} />
                  </div>
                )}
              </div>
            </div>
            <div className="mt-2 text-sm text-tf-text-secondary">
              Selected: {color}
            </div>
          </div>

          {error && (
            <div className="mb-4 p-3 bg-tf-negative/10 border border-tf-negative/20 text-tf-negative rounded text-sm">
              {error}
            </div>
          )}

          <div className="flex justify-end gap-2">
            <button
              type="button"
              onClick={onClose}
              className="px-4 py-2 text-tf-text-secondary hover:bg-tf-bg-elevated rounded transition"
              disabled={submitting}
            >
              Cancel
            </button>
            <button
              type="submit"
              className="px-4 py-2 bg-tf-accent-primary text-tf-text-primary rounded hover:bg-tf-accent-hover transition disabled:opacity-50"
              disabled={submitting}
            >
              {submitting ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
    </Modal>
  );
}
