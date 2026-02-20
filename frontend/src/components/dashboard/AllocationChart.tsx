/**
 * Donut chart visualization for allocation
 */

import type { AllocationData } from "@/types/dashboard";

interface Props {
  allocations: AllocationData[];
  totalValue: string;
}

export function AllocationChart({ allocations, totalValue }: Props) {
  if (allocations.length === 0) {
    return null;
  }

  // Calculate segments
  const total = parseFloat(totalValue);
  const segments = allocations.map((alloc) => ({
    name: alloc.asset_type_name,
    color: alloc.asset_type_color,
    percent: parseFloat(alloc.actual_percent),
    value: parseFloat(alloc.value),
  }));

  // SVG donut chart parameters
  const size = 300;
  const strokeWidth = 60;
  const radius = (size - strokeWidth) / 2;
  const center = size / 2;

  // Calculate segment paths
  type SegmentWithPath = typeof segments[number] & { path: string };
  const paths = segments.reduce<{ paths: SegmentWithPath[]; nextAngle: number }>((acc, segment) => {
    let angle = (segment.percent / 100) * 360;

    // SVG arcs can't handle exactly 360 degrees (start === end)
    // Cap at 359.99 for 100% allocations
    if (angle >= 360) {
      angle = 359.99;
    }

    const currentAngle = acc.nextAngle;
    const startAngle = currentAngle;
    const endAngle = currentAngle + angle;

    // Convert to radians
    const startRad = (startAngle * Math.PI) / 180;
    const endRad = (endAngle * Math.PI) / 180;

    // Calculate start and end points
    const startX = center + radius * Math.cos(startRad);
    const startY = center + radius * Math.sin(startRad);
    const endX = center + radius * Math.cos(endRad);
    const endY = center + radius * Math.sin(endRad);

    // Large arc flag if segment is more than 180 degrees
    const largeArcFlag = angle > 180 ? 1 : 0;

    // SVG path
    const path = [
      `M ${center} ${center}`,
      `L ${startX} ${startY}`,
      `A ${radius} ${radius} 0 ${largeArcFlag} 1 ${endX} ${endY}`,
      `Z`,
    ].join(" ");

    acc.paths.push({ ...segment, path });
    acc.nextAngle = endAngle;
    return acc;
  }, { paths: [], nextAngle: -90 }).paths;

  return (
    <div className="bg-tf-bg-surface border border-tf-border-subtle rounded-lg p-6">
      <h2 className="text-xl font-semibold mb-4">Allocation Breakdown</h2>

      <div className="flex flex-col items-center">
        {/* Donut Chart */}
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
          {/* Background circle */}
          <circle
            cx={center}
            cy={center}
            r={radius}
            fill="none"
            stroke="var(--bg-elevated)"
            strokeWidth={strokeWidth}
          />

          {/* Segments */}
          {paths.map((segment, index) => (
            <path
              key={index}
              d={segment.path}
              fill={segment.color}
              opacity={0.9}
              className="transition-opacity hover:opacity-100"
            />
          ))}

          {/* Center text */}
          <text
            x={center}
            y={center - 10}
            textAnchor="middle"
            className="text-2xl font-bold"
            fill="var(--text-primary)"
          >
            {total >= 1000
              ? `$${(total / 1000).toFixed(1)}k`
              : `$${total.toFixed(0)}`}
          </text>
          <text
            x={center}
            y={center + 15}
            textAnchor="middle"
            className="text-sm"
            fill="var(--text-secondary)"
          >
            Total Value
          </text>
        </svg>

        {/* Legend */}
        <div className="mt-6 grid grid-cols-2 gap-3 w-full">
          {segments.map((segment, index) => (
            <div key={index} className="flex items-center gap-2">
              <div
                className="w-4 h-4 rounded-full flex-shrink-0"
                style={{ backgroundColor: segment.color }}
              />
              <div className="text-sm">
                <div className="font-medium text-tf-text-primary truncate">
                  {segment.name}
                </div>
                <div className="text-tf-text-secondary">
                  {segment.percent.toFixed(1)}%
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
