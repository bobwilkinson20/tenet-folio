/**
 * Dialog for configuring provider credentials in-app.
 *
 * Fetches field definitions from the backend and renders a dynamic form.
 * On submit, validates credentials server-side and stores in Keychain.
 */

import { useEffect, useState } from "react";
import { providersApi } from "@/api";
import { Modal } from "@/components/common/Modal";
import type { ProviderSetupField } from "@/types/provider";
import { extractApiErrorMessage } from "@/utils/errors";

interface ProviderSetupDialogProps {
  providerName: string;
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function ProviderSetupDialog({
  providerName,
  isOpen,
  onClose,
  onSuccess,
}: ProviderSetupDialogProps) {
  const [fields, setFields] = useState<ProviderSetupField[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    // Reset state on open
    setFields([]);
    setValues({});
    setError(null);
    setSuccessMessage(null);
    setLoading(true);

    providersApi
      .getSetupInfo(providerName)
      .then((response) => {
        setFields(response.data);
      })
      .catch((err) => {
        setError(extractApiErrorMessage(err, "Failed to load setup info"));
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isOpen, providerName]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSubmitting(true);

    try {
      const response = await providersApi.setup(providerName, values);
      setSuccessMessage(response.data.message);
      onSuccess();
    } catch (err) {
      setError(extractApiErrorMessage(err, "Setup failed"));
    } finally {
      setSubmitting(false);
    }
  };

  const handleFieldChange = (key: string, value: string) => {
    setValues((prev) => ({ ...prev, [key]: value }));
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose}>
      <h2 className="text-lg font-semibold text-tf-text-primary mb-4">
        Configure {providerName}
      </h2>

      {loading && (
        <p className="text-tf-text-tertiary">Loading setup info...</p>
      )}

      {successMessage && (
        <div className="space-y-4">
          <p className="text-tf-positive">{successMessage}</p>
          <button
            onClick={onClose}
            className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90"
          >
            Done
          </button>
        </div>
      )}

      {!loading && !successMessage && error && fields.length === 0 && (
        <div className="space-y-4">
          <p className="text-sm text-tf-negative">{error}</p>
          <button
            type="button"
            onClick={onClose}
            className="rounded border border-tf-border-default px-4 py-2 text-sm font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
          >
            Close
          </button>
        </div>
      )}

      {!loading && !successMessage && fields.length > 0 && (
        <form onSubmit={handleSubmit} className="space-y-4">
          {fields.map((field) => (
            <div key={field.key}>
              <label
                htmlFor={`setup-${field.key}`}
                className="block text-sm font-medium text-tf-text-secondary mb-1"
              >
                {field.label}
              </label>
              {field.input_type === "textarea" ? (
                <textarea
                  id={`setup-${field.key}`}
                  value={values[field.key] ?? ""}
                  onChange={(e) => handleFieldChange(field.key, e.target.value)}
                  className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
                  rows={4}
                  required
                />
              ) : (
                <input
                  id={`setup-${field.key}`}
                  type={field.input_type === "password" ? "password" : "text"}
                  value={values[field.key] ?? ""}
                  onChange={(e) => handleFieldChange(field.key, e.target.value)}
                  className="w-full rounded border border-tf-border-default bg-tf-bg-base px-3 py-2 text-sm text-tf-text-primary focus:border-tf-accent-primary focus:outline-none"
                  required
                />
              )}
              {field.help_text && (
                <p className="mt-1 text-xs text-tf-text-tertiary">
                  {field.help_text}
                </p>
              )}
            </div>
          ))}

          {error && <p className="text-sm text-tf-negative">{error}</p>}

          <div className="flex justify-end gap-3 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="rounded border border-tf-border-default px-4 py-2 text-sm font-medium text-tf-text-secondary hover:bg-tf-bg-elevated"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className="rounded bg-tf-accent-primary px-4 py-2 text-sm font-medium text-white hover:bg-tf-accent-primary/90 disabled:opacity-50"
            >
              {submitting ? "Validating..." : "Save"}
            </button>
          </div>
        </form>
      )}
    </Modal>
  );
}
