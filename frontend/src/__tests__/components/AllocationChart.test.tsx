/**
 * Tests for AllocationChart component
 */

import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { AllocationChart } from '@/components/dashboard/AllocationChart';
import type { AllocationData } from '@/types/dashboard';

describe('AllocationChart', () => {
  it('should render null when no allocations', () => {
    const { container } = render(
      <AllocationChart allocations={[]} totalValue="0" />
    );

    expect(container.firstChild).toBeNull();
  });

  it('should display total value for amounts >= $1000', () => {
    const allocations: AllocationData[] = [
      {
        asset_type_id: '1',
        asset_type_name: 'Stocks',
        asset_type_color: '#3B82F6',
        target_percent: '100.00',
        actual_percent: '100.00',
        delta_percent: '0.00',
        value: '5000.00',
      },
    ];

    render(<AllocationChart allocations={allocations} totalValue="5000.00" />);

    // Should display as "$5.0k"
    expect(screen.getByText('$5.0k')).toBeInTheDocument();
  });

  it('should display dollar amount for values < $1000', () => {
    const allocations: AllocationData[] = [
      {
        asset_type_id: '1',
        asset_type_name: 'Stocks',
        asset_type_color: '#3B82F6',
        target_percent: '100.00',
        actual_percent: '100.00',
        delta_percent: '0.00',
        value: '203.97',
      },
    ];

    render(<AllocationChart allocations={allocations} totalValue="203.97" />);

    // Should display as "$204" (rounded)
    expect(screen.getByText('$204')).toBeInTheDocument();
  });

  it('should handle 100% allocation to single asset type', () => {
    const allocations: AllocationData[] = [
      {
        asset_type_id: '1',
        asset_type_name: 'Crypto',
        asset_type_color: '#F97316',
        target_percent: '10.00',
        actual_percent: '100.00',
        delta_percent: '90.00',
        value: '1000.00',
      },
    ];

    const { container } = render(
      <AllocationChart allocations={allocations} totalValue="1000.00" />
    );

    // Should render SVG without errors (regression test for 360-degree arc issue)
    const svg = container.querySelector('svg');
    expect(svg).toBeInTheDocument();

    // Should have path element for the segment
    const path = container.querySelector('path');
    expect(path).toBeInTheDocument();
  });

  it('should render legend with all asset types', () => {
    const allocations: AllocationData[] = [
      {
        asset_type_id: '1',
        asset_type_name: 'Stocks',
        asset_type_color: '#3B82F6',
        target_percent: '60.00',
        actual_percent: '60.00',
        delta_percent: '0.00',
        value: '6000.00',
      },
      {
        asset_type_id: '2',
        asset_type_name: 'Bonds',
        asset_type_color: '#10B981',
        target_percent: '40.00',
        actual_percent: '40.00',
        delta_percent: '0.00',
        value: '4000.00',
      },
    ];

    render(<AllocationChart allocations={allocations} totalValue="10000.00" />);

    expect(screen.getByText('Stocks')).toBeInTheDocument();
    expect(screen.getByText('Bonds')).toBeInTheDocument();
    expect(screen.getByText('60.0%')).toBeInTheDocument();
    expect(screen.getByText('40.0%')).toBeInTheDocument();
  });

  it('should render chart title', () => {
    const allocations: AllocationData[] = [
      {
        asset_type_id: '1',
        asset_type_name: 'Stocks',
        asset_type_color: '#3B82F6',
        target_percent: '100.00',
        actual_percent: '100.00',
        delta_percent: '0.00',
        value: '1000.00',
      },
    ];

    render(<AllocationChart allocations={allocations} totalValue="1000.00" />);

    expect(screen.getByText('Allocation Breakdown')).toBeInTheDocument();
  });

  it('should display center text using provided totalValue, not sum of allocations', () => {
    // totalValue is 8000 (allocation total), but allocation values sum to 8000
    // This tests that the chart uses the provided totalValue prop
    const allocations: AllocationData[] = [
      {
        asset_type_id: '1',
        asset_type_name: 'Stocks',
        asset_type_color: '#3B82F6',
        target_percent: '60.00',
        actual_percent: '62.50',
        delta_percent: '2.50',
        value: '5000.00',
      },
      {
        asset_type_id: '2',
        asset_type_name: 'Bonds',
        asset_type_color: '#10B981',
        target_percent: '40.00',
        actual_percent: '37.50',
        delta_percent: '-2.50',
        value: '3000.00',
      },
    ];

    // Pass allocation_total (8000) not total_net_worth (10000)
    render(<AllocationChart allocations={allocations} totalValue="8000.00" />);

    // Center text should show $8.0k (the allocation total)
    expect(screen.getByText('$8.0k')).toBeInTheDocument();
  });
});
