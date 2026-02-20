import { describe, it, expect, vi, beforeEach } from "vitest";
import { accountsApi } from "@/api/accounts";
import { apiClient } from "@/api/client";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    put: vi.fn(),
    delete: vi.fn(),
  },
}));

describe("accountsApi", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("getActivities", () => {
    it("should call GET /accounts/:id/activities without params", async () => {
      const mockResponse = { data: [] };
      vi.mocked(apiClient.get).mockResolvedValue(mockResponse);

      const result = await accountsApi.getActivities("acc-1");

      expect(apiClient.get).toHaveBeenCalledWith("/accounts/acc-1/activities", {
        params: undefined,
      });
      expect(result.data).toEqual([]);
    });

    it("should call GET /accounts/:id/activities with params", async () => {
      const mockActivity = {
        id: "act-1",
        account_id: "acc-1",
        type: "DIVIDEND",
        amount: "50.00",
      };
      vi.mocked(apiClient.get).mockResolvedValue({ data: [mockActivity] });

      const result = await accountsApi.getActivities("acc-1", {
        limit: 10,
        offset: 0,
        activity_type: "DIVIDEND",
      });

      expect(apiClient.get).toHaveBeenCalledWith("/accounts/acc-1/activities", {
        params: { limit: 10, offset: 0, activity_type: "DIVIDEND" },
      });
      expect(result.data).toHaveLength(1);
    });
  });

  describe("list", () => {
    it("should call GET /accounts", async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

      await accountsApi.list();

      expect(apiClient.get).toHaveBeenCalledWith("/accounts");
    });
  });

  describe("get", () => {
    it("should call GET /accounts/:id", async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: { id: "acc-1" } });

      await accountsApi.get("acc-1");

      expect(apiClient.get).toHaveBeenCalledWith("/accounts/acc-1");
    });
  });

  describe("getHoldings", () => {
    it("should call GET /accounts/:id/holdings", async () => {
      vi.mocked(apiClient.get).mockResolvedValue({ data: [] });

      await accountsApi.getHoldings("acc-1");

      expect(apiClient.get).toHaveBeenCalledWith("/accounts/acc-1/holdings");
    });
  });

  describe("createManual", () => {
    it("should call POST /accounts/manual", async () => {
      vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "acc-new" } });

      await accountsApi.createManual({ name: "My House" });

      expect(apiClient.post).toHaveBeenCalledWith("/accounts/manual", {
        name: "My House",
      });
    });

    it("should pass institution_name when provided", async () => {
      vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "acc-new" } });

      await accountsApi.createManual({
        name: "Savings",
        institution_name: "Local Bank",
      });

      expect(apiClient.post).toHaveBeenCalledWith("/accounts/manual", {
        name: "Savings",
        institution_name: "Local Bank",
      });
    });
  });

  describe("addHolding", () => {
    it("should call POST /accounts/:id/holdings", async () => {
      vi.mocked(apiClient.post).mockResolvedValue({ data: { id: "h-1" } });

      await accountsApi.addHolding("acc-1", {
        ticker: "HOME",
        quantity: 1,
        market_value: 500000,
      });

      expect(apiClient.post).toHaveBeenCalledWith("/accounts/acc-1/holdings", {
        ticker: "HOME",
        quantity: 1,
        market_value: 500000,
      });
    });
  });

  describe("updateHolding", () => {
    it("should call PUT /accounts/:id/holdings/:holdingId", async () => {
      vi.mocked(apiClient.put).mockResolvedValue({ data: { id: "h-1" } });

      await accountsApi.updateHolding("acc-1", "h-1", {
        ticker: "HOME",
        market_value: 520000,
      });

      expect(apiClient.put).toHaveBeenCalledWith(
        "/accounts/acc-1/holdings/h-1",
        { ticker: "HOME", market_value: 520000 },
      );
    });
  });

  describe("delete", () => {
    it("should call DELETE /accounts/:id", async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({});

      await accountsApi.delete("acc-1");

      expect(apiClient.delete).toHaveBeenCalledWith("/accounts/acc-1");
    });
  });

  describe("deleteHolding", () => {
    it("should call DELETE /accounts/:id/holdings/:holdingId", async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({});

      await accountsApi.deleteHolding("acc-1", "h-1");

      expect(apiClient.delete).toHaveBeenCalledWith(
        "/accounts/acc-1/holdings/h-1",
      );
    });
  });
});
