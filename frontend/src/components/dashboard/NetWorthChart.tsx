import { useState, useEffect, useMemo, useCallback } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { portfolioApi } from "@/api";
import type { ValuePoint } from "@/types/portfolio";
import { formatCurrency, formatCurrencyShort } from "@/utils/format";

type TimeRange = "1M" | "3M" | "6M" | "YTD" | "1Y" | "ALL";

const TIME_RANGES: TimeRange[] = ["1M", "3M", "6M", "YTD", "1Y", "ALL"];

function getStartDateForRange(range: TimeRange): string | undefined {
  if (range === "ALL") return undefined;

  const now = new Date();
  let start: Date;

  switch (range) {
    case "1M":
      start = new Date(now.getFullYear(), now.getMonth() - 1, now.getDate());
      break;
    case "3M":
      start = new Date(now.getFullYear(), now.getMonth() - 3, now.getDate());
      break;
    case "6M":
      start = new Date(now.getFullYear(), now.getMonth() - 6, now.getDate());
      break;
    case "YTD":
      start = new Date(now.getFullYear(), 0, 1);
      break;
    case "1Y":
      start = new Date(now.getFullYear() - 1, now.getMonth(), now.getDate());
      break;
  }

  return start.toISOString().split("T")[0];
}

function formatDateShort(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function formatDateFull(dateStr: string): string {
  const d = new Date(dateStr + "T00:00:00");
  return d.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

interface ChartDataPoint {
  date: string;
  value: number;
  label: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: Array<{ payload: ChartDataPoint }>;
}

function CustomTooltip({ active, payload }: CustomTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const data = payload[0].payload;
  return (
    <div className="bg-tf-bg-elevated border border-tf-border-default rounded-lg px-3 py-2">
      <p className="text-xs text-tf-text-tertiary">{formatDateFull(data.date)}</p>
      <p className="text-sm font-semibold text-tf-text-primary">
        {formatCurrency(data.value)}
      </p>
    </div>
  );
}

interface NetWorthChartProps {
  allocationOnly?: boolean;
  accountIds?: string;
}

export function NetWorthChart({ allocationOnly, accountIds }: NetWorthChartProps) {
  const [range, setRange] = useState<TimeRange>("3M");
  const [dataPoints, setDataPoints] = useState<ValuePoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async (selectedRange: TimeRange) => {
    setLoading(true);
    setError(null);
    try {
      const start = getStartDateForRange(selectedRange);
      const response = await portfolioApi.getValueHistory({
        start,
        group_by: "total",
        allocation_only: allocationOnly || undefined,
        account_ids: accountIds,
      });
      setDataPoints(response.data.data_points ?? []);
    } catch {
      setError("Failed to load portfolio history");
    } finally {
      setLoading(false);
    }
  }, [allocationOnly, accountIds]);

  useEffect(() => {
    fetchData(range);
  }, [range, fetchData]);

  const chartData: ChartDataPoint[] = useMemo(
    () =>
      dataPoints.map((p) => ({
        date: p.date,
        value: parseFloat(p.value),
        label: formatDateShort(p.date),
      })),
    [dataPoints]
  );

  // Don't render if no data and not loading
  if (!loading && chartData.length === 0 && !error) {
    return null;
  }

  return (
    <div className="bg-tf-bg-surface rounded-lg border border-tf-border-subtle p-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-lg font-semibold text-tf-text-primary">
          Portfolio Value
        </h3>
        <div className="flex gap-1">
          {TIME_RANGES.map((r) => (
            <button
              key={r}
              onClick={() => setRange(r)}
              className={`px-2.5 py-1 text-xs font-medium rounded-md transition-colors ${
                range === r
                  ? "bg-tf-accent-primary text-tf-text-primary"
                  : "bg-tf-bg-elevated text-tf-text-secondary hover:text-tf-text-primary"
              }`}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <p className="text-tf-text-tertiary text-sm">Loading chart...</p>
        </div>
      ) : error ? (
        <div className="flex items-center justify-center h-64">
          <p className="text-tf-negative text-sm">{error}</p>
        </div>
      ) : (
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart
            data={chartData}
            margin={{ top: 5, right: 5, left: 5, bottom: 5 }}
          >
            <defs>
              <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--accent-primary)" stopOpacity={0.15} />
                <stop offset="95%" stopColor="var(--accent-primary)" stopOpacity={0.01} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="var(--border-subtle)"
              vertical={false}
            />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
              tickLine={false}
              axisLine={{ stroke: "var(--border-default)" }}
              interval="preserveStartEnd"
              minTickGap={40}
            />
            <YAxis
              tickFormatter={formatCurrencyShort}
              tick={{ fontSize: 11, fill: "var(--text-tertiary)" }}
              tickLine={false}
              axisLine={false}
              width={60}
              domain={["auto", "auto"]}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="value"
              stroke="var(--accent-primary)"
              strokeWidth={2}
              fill="url(#valueGradient)"
              dot={false}
              activeDot={{ r: 4, fill: "var(--accent-primary)", stroke: "var(--bg-surface)", strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}
