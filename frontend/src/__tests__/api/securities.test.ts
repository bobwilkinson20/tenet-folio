/**
 * Tests for securities API client
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { securitiesApi } from '@/api/securities';
import { apiClient } from '@/api/client';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    patch: vi.fn(),
  },
}));

describe('securitiesApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('should call GET /securities without params', async () => {
      const mockResponse = {
        data: [
          { id: '1', ticker: 'AAPL', name: 'Apple Inc.', asset_type_id: null },
        ],
      };
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse);

      const result = await securitiesApi.list();

      expect(apiClient.get).toHaveBeenCalledWith('/securities', { params: undefined });
      expect(result.data).toHaveLength(1);
    });

    it('should call GET /securities with search param', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

      await securitiesApi.list({ search: 'AAPL' });

      expect(apiClient.get).toHaveBeenCalledWith('/securities', {
        params: { search: 'AAPL' },
      });
    });

    it('should call GET /securities with unassigned_only param', async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

      await securitiesApi.list({ unassigned_only: true });

      expect(apiClient.get).toHaveBeenCalledWith('/securities', {
        params: { unassigned_only: true },
      });
    });
  });

  describe('getUnassigned', () => {
    it('should call GET /securities/unassigned', async () => {
      const mockResponse = {
        data: {
          count: 5,
          items: [
            { id: '1', ticker: 'AAPL', name: 'Apple Inc.', asset_type_id: null },
          ],
        },
      };
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse);

      const result = await securitiesApi.getUnassigned();

      expect(apiClient.get).toHaveBeenCalledWith('/securities/unassigned');
      expect(result.data.count).toBe(5);
    });
  });

  describe('updateType', () => {
    it('should call PATCH /securities/:id with asset type', async () => {
      const mockResponse = {
        data: { id: '1', ticker: 'AAPL', manual_asset_class_id: 'type-1' },
      };
      vi.mocked(apiClient.patch).mockResolvedValue(mockResponse);

      const result = await securitiesApi.updateType('1', 'type-1');

      expect(apiClient.patch).toHaveBeenCalledWith('/securities/1', {
        manual_asset_class_id: 'type-1',
      });
      expect(result.data.manual_asset_class_id).toBe('type-1');
    });

    it('should allow null asset type for unassignment', async () => {
      const mockResponse = {
        data: { id: '1', ticker: 'AAPL', manual_asset_class_id: null },
      };
      vi.mocked(apiClient.patch).mockResolvedValue(mockResponse);

      const result = await securitiesApi.updateType('1', null);

      expect(apiClient.patch).toHaveBeenCalledWith('/securities/1', {
        manual_asset_class_id: null,
      });
      expect(result.data.manual_asset_class_id).toBeNull();
    });
  });
});
