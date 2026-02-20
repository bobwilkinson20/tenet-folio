import type { Activity } from "../../types";

interface ActivityListProps {
  activities: Activity[];
  loading: boolean;
}

function formatAmount(amount: string | null): { text: string; colorClass: string } {
  if (amount == null) return { text: "-", colorClass: "text-tf-text-tertiary" };

  const value = Number(amount);
  const formatted = `$${Math.abs(value).toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`;

  if (value > 0) return { text: formatted, colorClass: "text-tf-positive" };
  if (value < 0) return { text: `-${formatted}`, colorClass: "text-tf-negative" };
  return { text: formatted, colorClass: "text-tf-text-tertiary" };
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString();
}

function formatType(type: string): string {
  return type.charAt(0).toUpperCase() + type.slice(1).toLowerCase();
}

export function ActivityList({ activities, loading }: ActivityListProps) {
  if (loading) {
    return <div className="p-6 text-tf-text-tertiary">Loading activity...</div>;
  }

  return (
    <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-lg overflow-hidden">
      <table className="min-w-full divide-y divide-tf-border-default">
        <thead className="bg-tf-bg-surface">
          <tr>
            <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
              Date
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
              Type
            </th>
            <th className="px-6 py-3 text-left text-xs font-medium text-tf-text-tertiary uppercase">
              Description
            </th>
            <th className="px-6 py-3 text-right text-xs font-medium text-tf-text-tertiary uppercase">
              Amount
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-tf-border-subtle">
          {activities.length === 0 ? (
            <tr>
              <td
                colSpan={4}
                className="px-6 py-4 text-center text-tf-text-tertiary"
              >
                No activity found.
              </td>
            </tr>
          ) : (
            activities.map((a) => {
              const { text, colorClass } = formatAmount(a.amount);
              return (
                <tr key={a.id}>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-tf-text-primary">
                    {formatDate(a.activity_date)}
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-tf-text-tertiary">
                    {formatType(a.type)}
                  </td>
                  <td className="px-6 py-4 text-sm text-tf-text-tertiary">
                    {a.description || "-"}
                  </td>
                  <td className={`px-6 py-4 whitespace-nowrap text-right text-sm font-medium ${colorClass}`}>
                    {text}
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}
