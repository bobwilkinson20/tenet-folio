/**
 * Alert banner for unassigned securities
 */

import { Link } from "react-router-dom";

interface Props {
  count: number;
  value: string;
}

export function UnassignedAlert({ count, value }: Props) {
  if (count === 0) {
    return null;
  }

  const valueNum = parseFloat(value);

  return (
    <div className="bg-tf-warning/10 border border-tf-warning/20 rounded-lg p-4">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0">
          <svg
            className="w-6 h-6 text-tf-warning"
            fill="none"
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div className="flex-1">
          <h3 className="text-sm font-medium text-tf-warning">
            {count} {count === 1 ? "security needs" : "securities need"} type
            assignment
          </h3>
          <div className="mt-2 text-sm text-tf-warning">
            <p>
              Unassigned securities (
              {valueNum > 0
                ? `$${valueNum.toLocaleString(undefined, {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2,
                  })}`
                : "$0"}
              ) are not included in your allocation calculations.
            </p>
          </div>
          <div className="mt-3">
            <Link
              to="/settings?tab=securities"
              className="text-sm font-medium text-tf-warning hover:text-tf-text-primary underline"
            >
              Assign Types →
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
