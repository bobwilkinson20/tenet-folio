/**
 * Tests for AssetTypeSelect component
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { AssetTypeSelect } from '@/components/common/AssetTypeSelect';
import type { AssetType } from '@/types/assetType';

const mockAssetTypes: AssetType[] = [
  {
    id: '1',
    name: 'Stocks',
    color: '#3B82F6',
    target_percent: 60,
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  },
  {
    id: '2',
    name: 'Bonds',
    color: '#10B981',
    target_percent: 40,
    created_at: '2024-01-01',
    updated_at: '2024-01-01',
  },
];

describe('AssetTypeSelect', () => {
  it('should render with placeholder when no value selected', () => {
    render(
      <AssetTypeSelect
        value={null}
        onChange={vi.fn()}
        assetTypes={mockAssetTypes}
        placeholder="Select type"
      />
    );

    expect(screen.getByText('Select type')).toBeInTheDocument();
  });

  it('should display selected asset type name', () => {
    render(
      <AssetTypeSelect
        value="1"
        onChange={vi.fn()}
        assetTypes={mockAssetTypes}
      />
    );

    expect(screen.getByText('Stocks')).toBeInTheDocument();
  });

  it('should call onChange when selection changes', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <AssetTypeSelect
        value={null}
        onChange={onChange}
        assetTypes={mockAssetTypes}
      />
    );

    // Click to open dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Select "Stocks"
    const stocksOption = screen.getByText('Stocks');
    await user.click(stocksOption);

    expect(onChange).toHaveBeenCalledWith('1');
  });

  it('should allow clearing selection by choosing placeholder', async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();

    render(
      <AssetTypeSelect
        value="1"
        onChange={onChange}
        assetTypes={mockAssetTypes}
        placeholder="None"
      />
    );

    // Open dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Select "None" option
    const noneOption = screen.getByText('None');
    await user.click(noneOption);

    expect(onChange).toHaveBeenCalledWith(null);
  });

  it('should be disabled when disabled prop is true', () => {
    render(
      <AssetTypeSelect
        value={null}
        onChange={vi.fn()}
        assetTypes={mockAssetTypes}
        disabled={true}
      />
    );

    const button = screen.getByRole('button');
    expect(button).toBeDisabled();
  });

  it('should render all asset types in dropdown', async () => {
    const user = userEvent.setup();

    render(
      <AssetTypeSelect
        value={null}
        onChange={vi.fn()}
        assetTypes={mockAssetTypes}
      />
    );

    // Open dropdown
    const button = screen.getByRole('button');
    await user.click(button);

    // Check all types are present
    expect(screen.getByText('Stocks')).toBeInTheDocument();
    expect(screen.getByText('Bonds')).toBeInTheDocument();
  });
});
