/**
 * Tests for TargetAllocationForm component
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { TargetAllocationForm } from '@/components/settings/TargetAllocationForm';

vi.mock('@/api', () => ({
  assetTypeApi: {
    list: vi.fn(),
  },
  portfolioApi: {
    getAllocation: vi.fn(),
    updateAllocation: vi.fn(),
  },
}));

const mockSetDashboardStale = vi.fn();

vi.mock('@/context', () => ({
  usePortfolioContext: () => ({
    setDashboardStale: mockSetDashboardStale,
  }),
}));

import { assetTypeApi, portfolioApi } from '@/api';

const mockAssetTypes = [
  {
    id: '1',
    name: 'Stocks',
    color: '#3B82F6',
    target_percent: '60.00',
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  },
  {
    id: '2',
    name: 'Bonds',
    color: '#10B981',
    target_percent: '40.00',
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  },
];

describe('TargetAllocationForm', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockSetDashboardStale.mockClear();
    vi.mocked(assetTypeApi.list).mockResolvedValue({
      data: {
        items: mockAssetTypes,
        total_target_percent: '100.00',
      },
    } as never);
    vi.mocked(portfolioApi.getAllocation).mockResolvedValue({
      data: {
        allocations: [
          { asset_type_id: '1', target_percent: '60.00' },
          { asset_type_id: '2', target_percent: '40.00' },
        ],
        total_percent: '100.00',
        is_valid: true,
      },
    } as never);
  });

  it('should load and display asset types', async () => {
    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
      expect(screen.getByText('Bonds')).toBeInTheDocument();
    });
  });

  it('should show current target percentages in inputs', async () => {
    render(<TargetAllocationForm />);

    await waitFor(() => {
      const stocksInput = screen.getByDisplayValue('60');
      const bondsInput = screen.getByDisplayValue('40');
      expect(stocksInput).toBeInTheDocument();
      expect(bondsInput).toBeInTheDocument();
    });
  });

  it('should calculate total percentage in real-time', async () => {
    const user = userEvent.setup();
    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    // Initially should show 100.00%
    expect(screen.getByText(/100\.00%/)).toBeInTheDocument();

    // Change stocks to 70
    const stocksInput = screen.getByDisplayValue('60');
    await user.clear(stocksInput);
    await user.type(stocksInput, '70.00');

    // Total should update to 110.00%
    await waitFor(() => {
      expect(screen.getByText(/110\.00%/)).toBeInTheDocument();
    });
  });

  it('should show green checkmark when total is 100%', async () => {
    render(<TargetAllocationForm />);

    await waitFor(() => {
      // Should have success indicator (green checkmark)
      const successIndicator = screen.getByText('✓');
      expect(successIndicator).toHaveClass('text-tf-positive');
    });
  });

  it('should show red X when total is not 100%', async () => {
    const user = userEvent.setup();
    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    // Change to invalid total
    const stocksInput = screen.getByDisplayValue('60');
    await user.clear(stocksInput);
    await user.type(stocksInput, '50.00');

    await waitFor(() => {
      const errorIndicator = screen.getByText('✗');
      expect(errorIndicator).toHaveClass('text-tf-negative');
    });
  });

  it('should disable save button when total is not 100%', async () => {
    const user = userEvent.setup();
    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    const saveButton = screen.getByText('Save');

    // Initially enabled (total is 100%)
    expect(saveButton).not.toBeDisabled();

    // Change to invalid total
    const stocksInput = screen.getByDisplayValue('60');
    await user.clear(stocksInput);
    await user.type(stocksInput, '50.00');

    await waitFor(() => {
      expect(saveButton).toBeDisabled();
    });
  });

  it('should call API to save allocation when valid', async () => {
    const user = userEvent.setup();
    vi.mocked(portfolioApi.updateAllocation).mockResolvedValue({
      data: {
        allocations: [],
        total_percent: '100.00',
        is_valid: true,
      },
    } as never);

    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    const saveButton = screen.getByText('Save');
    await user.click(saveButton);

    await waitFor(() => {
      expect(portfolioApi.updateAllocation).toHaveBeenCalledWith([
        { asset_type_id: '1', target_percent: 60 },
        { asset_type_id: '2', target_percent: 40 },
      ]);
    });
  });

  it('should show success message after successful save', async () => {
    const user = userEvent.setup();
    vi.mocked(portfolioApi.updateAllocation).mockResolvedValue({
      data: {
        allocations: [],
        total_percent: '100.00',
        is_valid: true,
      },
    } as never);

    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    const saveButton = screen.getByText('Save');
    await user.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText(/saved successfully/i)).toBeInTheDocument();
    });
  });

  it('should mark dashboard as stale after successful save', async () => {
    const user = userEvent.setup();
    vi.mocked(portfolioApi.updateAllocation).mockResolvedValue({
      data: {
        allocations: [],
        total_percent: '100.00',
        is_valid: true,
      },
    } as never);

    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    const saveButton = screen.getByText('Save');
    await user.click(saveButton);

    await waitFor(() => {
      expect(mockSetDashboardStale).toHaveBeenCalledWith(true);
    });
  });

  it('should not mark dashboard as stale when save fails', async () => {
    const user = userEvent.setup();
    vi.mocked(portfolioApi.updateAllocation).mockRejectedValue({
      response: { data: { detail: 'Save failed' } },
    });

    render(<TargetAllocationForm />);

    await waitFor(() => {
      expect(screen.getByText('Stocks')).toBeInTheDocument();
    });

    const saveButton = screen.getByText('Save');
    await user.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText('Save failed')).toBeInTheDocument();
    });

    expect(mockSetDashboardStale).not.toHaveBeenCalled();
  });
});
