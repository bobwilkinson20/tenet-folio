/**
 * Tests for asset types API client
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { assetTypeApi } from '@/api/assetTypes';
import { apiClient } from '@/api/client';

vi.mock('@/api/client', () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

describe('assetTypeApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('list', () => {
    it('should call GET /asset-types', async () => {
      const mockResponse = {
        data: {
          items: [
            { id: '1', name: 'Stocks', color: '#3B82F6', target_percent: '60.00' },
          ],
          total_target_percent: '60.00',
        },
      };
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse);

      const result = await assetTypeApi.list();

      expect(apiClient.get).toHaveBeenCalledWith('/asset-types');
      expect(result.data.items).toHaveLength(1);
      expect(result.data.items[0].name).toBe('Stocks');
    });
  });

  describe('get', () => {
    it('should call GET /asset-types/:id', async () => {
      const mockResponse = {
        data: {
          id: '1',
          name: 'Stocks',
          color: '#3B82F6',
          target_percent: '60.00',
          security_count: 5,
          account_count: 2,
        },
      };
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse);

      const result = await assetTypeApi.get('1');

      expect(apiClient.get).toHaveBeenCalledWith('/asset-types/1');
      expect(result.data.name).toBe('Stocks');
      expect(result.data.security_count).toBe(5);
    });
  });

  describe('create', () => {
    it('should call POST /asset-types with data', async () => {
      const createData = { name: 'Bonds', color: '#10B981' };
      const mockResponse = {
        data: { id: '2', ...createData, target_percent: '0.00' },
      };
      vi.mocked(apiClient.post).mockResolvedValue(mockResponse);

      const result = await assetTypeApi.create(createData);

      expect(apiClient.post).toHaveBeenCalledWith('/asset-types', createData);
      expect(result.data.name).toBe('Bonds');
    });
  });

  describe('update', () => {
    it('should call PATCH /asset-types/:id with data', async () => {
      const updateData = { name: 'US Equities' };
      const mockResponse = {
        data: { id: '1', name: 'US Equities', color: '#3B82F6', target_percent: '60.00' },
      };
      vi.mocked(apiClient.patch).mockResolvedValue(mockResponse);

      const result = await assetTypeApi.update('1', updateData);

      expect(apiClient.patch).toHaveBeenCalledWith('/asset-types/1', updateData);
      expect(result.data.name).toBe('US Equities');
    });
  });

  describe('delete', () => {
    it('should call DELETE /asset-types/:id', async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({ data: null });

      await assetTypeApi.delete('1');

      expect(apiClient.delete).toHaveBeenCalledWith('/asset-types/1');
    });
  });
});
