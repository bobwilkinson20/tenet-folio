/**
 * Tests for portfolio allocation API client
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { portfolioApi } from '@/api/portfolio';
import { apiClient } from '@/api/client';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    put: vi.fn(),
  },
}));

describe('portfolioApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAllocation', () => {
    it('should call GET /portfolio/allocation', async () => {
      const mockResponse = {
        data: {
          allocations: [
            { asset_type_id: '1', target_percent: 60 },
            { asset_type_id: '2', target_percent: 40 },
          ],
          total_percent: 100,
          is_valid: true,
        },
      };
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse);

      const result = await portfolioApi.getAllocation();

      expect(apiClient.get).toHaveBeenCalledWith('/portfolio/allocation');
      expect(result.data.allocations).toHaveLength(2);
      expect(result.data.is_valid).toBe(true);
    });
  });

  describe('updateAllocation', () => {
    it('should call PUT /portfolio/allocation with valid 100% allocation', async () => {
      const allocations = [
        { asset_type_id: '1', target_percent: 70 },
        { asset_type_id: '2', target_percent: 30 },
      ];
      const mockResponse = {
        data: {
          allocations,
          total_percent: 100,
          is_valid: true,
        },
      };
      vi.mocked(apiClient.put).mockResolvedValue(mockResponse);

      const result = await portfolioApi.updateAllocation(allocations);

      expect(apiClient.put).toHaveBeenCalledWith('/portfolio/allocation', {
        allocations,
      });
      expect(result.data.is_valid).toBe(true);
    });

    it('should handle invalid allocation totals', async () => {
      const allocations = [
        { asset_type_id: '1', target_percent: 60 },
        { asset_type_id: '2', target_percent: 30 },
      ];

      vi.mocked(apiClient.put).mockRejectedValue({
        response: {
          status: 400,
          data: { detail: 'Target allocations must sum to 100%, got 90.00%' },
        },
      });

      await expect(portfolioApi.updateAllocation(allocations)).rejects.toMatchObject({
        response: {
          status: 400,
        },
      });
    });
  });
});
