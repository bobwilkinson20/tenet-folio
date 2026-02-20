import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { CashFlowReviewPage } from "../../pages/CashFlowReview";
import type { Activity } from "../../types";
import type { CashFlowAccountSummary } from "../../types/activity";

const mockSummaries: CashFlowAccountSummary[] = [
  {
    account_id: "acc-1",
    account_name: "Checking",
    total_inflows: "5000.00",
    total_outflows: "-2000.00",
    net_flow: "3000.00",
    activity_count: 4,
    unreviewed_count: 2,
  },
  {
    account_id: "acc-2",
    account_name: "Savings",
    total_inflows: "1000.00",
    total_outflows: "-500.00",
    net_flow: "500.00",
    activity_count: 2,
    unreviewed_count: 0,
  },
];

const makeActivity = (overrides: Partial<Activity> = {}): Activity => ({
  id: "act-1",
  account_id: "acc-1",
  provider_name: "Manual",
  external_id: "ext-1",
  activity_date: "2025-06-15T00:00:00Z",
  settlement_date: null,
  type: "deposit",
  description: "Direct deposit",
  ticker: null,
  units: null,
  price: null,
  amount: "2500.00",
  currency: "USD",
  fee: null,
  is_reviewed: false,
  notes: null,
  user_modified: false,
  created_at: "2025-06-15T12:00:00Z",
  ...overrides,
});

const mockActivities: Activity[] = [
  makeActivity({ id: "act-1", type: "deposit", amount: "2500.00", is_reviewed: false }),
  makeActivity({
    id: "act-2",
    type: "withdrawal",
    amount: "1000.00",
    is_reviewed: true,
    user_modified: true,
    notes: "ATM withdrawal",
  }),
  makeActivity({ id: "act-3", type: "transfer_in", amount: "500.00", is_reviewed: false }),
];

// Mocks
const mockGetCashFlowSummary = vi.fn();
const mockGetActivities = vi.fn();
const mockCreateActivity = vi.fn();
const mockUpdateActivity = vi.fn();
const mockDeleteActivity = vi.fn();
const mockMarkActivitiesReviewed = vi.fn();

vi.mock("../../api/portfolio", () => ({
  portfolioApi: {
    getCashFlowSummary: (...args: unknown[]) => mockGetCashFlowSummary(...args),
  },
}));

vi.mock("../../api/accounts", () => ({
  accountsApi: {
    getActivities: (...args: unknown[]) => mockGetActivities(...args),
    createActivity: (...args: unknown[]) => mockCreateActivity(...args),
    updateActivity: (...args: unknown[]) => mockUpdateActivity(...args),
    deleteActivity: (...args: unknown[]) => mockDeleteActivity(...args),
    markActivitiesReviewed: (...args: unknown[]) => mockMarkActivitiesReviewed(...args),
  },
}));

const stableGetPreference = <T,>(_key: string, defaultValue: T): T => defaultValue;
const stableSetPreference = vi.fn();

vi.mock("../../hooks", () => ({
  usePreferences: vi.fn(() => ({
    loading: false,
    getPreference: stableGetPreference,
    setPreference: stableSetPreference,
  })),
}));

function renderPage() {
  return render(
    <MemoryRouter>
      <CashFlowReviewPage />
    </MemoryRouter>,
  );
}

async function expandAccount() {
  renderPage();
  await waitFor(() => {
    expect(screen.getByTestId("account-row-acc-1")).toBeInTheDocument();
  });
  fireEvent.click(screen.getByTestId("account-row-acc-1"));
  await waitFor(() => {
    expect(screen.getByTestId("activity-row-act-1")).toBeInTheDocument();
  });
}

describe("CashFlowReviewPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetCashFlowSummary.mockResolvedValue({ data: mockSummaries });
    mockGetActivities.mockResolvedValue({ data: mockActivities });
    mockCreateActivity.mockResolvedValue({ data: makeActivity({ id: "act-new" }) });
    mockUpdateActivity.mockResolvedValue({
      data: makeActivity({ id: "act-1", type: "withdrawal", user_modified: true }),
    });
    mockMarkActivitiesReviewed.mockResolvedValue({ data: { updated_count: 2 } });
  });

  it("renders loading state initially", () => {
    mockGetCashFlowSummary.mockReturnValue(new Promise(() => {})); // never resolves
    renderPage();
    expect(screen.getByText("Loading...")).toBeInTheDocument();
  });

  it("renders account summary rows from API data", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("account-row-acc-1")).toBeInTheDocument();
      expect(screen.getByTestId("account-row-acc-2")).toBeInTheDocument();
    });
  });

  it("shows unreviewed badge for accounts with unreviewed activities", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("unreviewed-badge-acc-1")).toHaveTextContent("2 unreviewed");
    });
    expect(screen.queryByTestId("unreviewed-badge-acc-2")).not.toBeInTheDocument();
  });

  it("expanding an account row fetches and shows activities", async () => {
    await expandAccount();
    expect(mockGetActivities).toHaveBeenCalledWith("acc-1", expect.objectContaining({ limit: 500 }));
    expect(screen.getByTestId("activity-row-act-1")).toBeInTheDocument();
    expect(screen.getByTestId("activity-row-act-2")).toBeInTheDocument();
  });

  it("Add Activity button opens modal, POST creates activity", async () => {
    await expandAccount();

    fireEvent.click(screen.getByTestId("add-activity-btn"));
    await waitFor(() => {
      expect(screen.getByText("Add Activity")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId("add-date"), { target: { value: "2025-07-01" } });
    fireEvent.change(screen.getByTestId("add-amount"), { target: { value: "100" } });

    fireEvent.click(screen.getByTestId("add-submit"));
    await waitFor(() => {
      expect(mockCreateActivity).toHaveBeenCalledWith("acc-1", expect.objectContaining({
        activity_date: "2025-07-01T00:00:00",
        type: "deposit",
      }));
    });
  });

  it("clicking a type cell opens a select for that cell only", async () => {
    await expandAccount();

    fireEvent.click(screen.getByTestId("type-cell-act-1"));

    await waitFor(() => {
      expect(screen.getByTestId("edit-type")).toBeInTheDocument();
    });

    // No save/cancel buttons in auto-save mode
    expect(screen.queryByTestId("edit-save")).not.toBeInTheDocument();
    expect(screen.queryByTestId("edit-cancel")).not.toBeInTheDocument();
  });

  it("clicking an amount cell opens an input for that cell only", async () => {
    await expandAccount();

    fireEvent.click(screen.getByTestId("amount-cell-act-1"));
    await waitFor(() => {
      expect(screen.getByTestId("edit-amount")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("edit-save")).not.toBeInTheDocument();
  });

  it("clicking a notes cell opens an input for that cell only", async () => {
    await expandAccount();

    fireEvent.click(screen.getByTestId("notes-cell-act-1"));
    await waitFor(() => {
      expect(screen.getByTestId("edit-notes")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("edit-save")).not.toBeInTheDocument();
  });

  it("selecting a new type auto-saves via PATCH", async () => {
    await expandAccount();

    fireEvent.click(screen.getByTestId("type-cell-act-1"));
    await waitFor(() => {
      expect(screen.getByTestId("edit-type")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId("edit-type"), { target: { value: "withdrawal" } });
    await waitFor(() => {
      expect(mockUpdateActivity).toHaveBeenCalledWith("acc-1", "act-1", {
        type: "withdrawal",
      });
    });
  });

  it("blurring a type select without changing value reverts to display", async () => {
    await expandAccount();

    fireEvent.click(screen.getByTestId("type-cell-act-1"));
    await waitFor(() => {
      expect(screen.getByTestId("edit-type")).toBeInTheDocument();
    });

    fireEvent.blur(screen.getByTestId("edit-type"));
    await waitFor(() => {
      expect(screen.queryByTestId("edit-type")).not.toBeInTheDocument();
    });
    expect(screen.getByTestId("type-cell-act-1")).toBeInTheDocument();
  });

  it("Mark All as Reviewed calls bulk endpoint per account", async () => {
    window.confirm = vi.fn(() => true);

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("account-row-acc-1")).toBeInTheDocument();
    });

    const markBtn = screen.getByTestId("mark-all-reviewed");
    expect(markBtn).toHaveTextContent("Mark All as Reviewed (2)");

    fireEvent.click(markBtn);

    await waitFor(() => {
      expect(window.confirm).toHaveBeenCalled();
      expect(mockGetActivities).toHaveBeenCalledWith("acc-1", expect.objectContaining({ reviewed: false }));
    });

    await waitFor(() => {
      expect(mockMarkActivitiesReviewed).toHaveBeenCalledWith("acc-1", ["act-1", "act-3"]);
    });
  });

  it("filter toggles update API calls correctly", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("account-row-acc-1")).toBeInTheDocument();
    });

    fireEvent.change(screen.getByTestId("start-date"), { target: { value: "2025-01-01" } });

    await waitFor(() => {
      expect(mockGetCashFlowSummary).toHaveBeenCalledWith(
        expect.objectContaining({ start_date: "2025-01-01" }),
      );
    });
  });

  it("modified indicator shows on user_modified activities", async () => {
    await expandAccount();
    expect(screen.getByTestId("modified-indicator-act-2")).toBeInTheDocument();
    expect(screen.queryByTestId("modified-indicator-act-1")).not.toBeInTheDocument();
  });

  it("shows empty state when no summaries returned", async () => {
    mockGetCashFlowSummary.mockResolvedValue({ data: [] });
    renderPage();
    await waitFor(() => {
      expect(screen.getByText("No cash flow activities found.")).toBeInTheDocument();
    });
  });

  it("unreviewed toggle button is active by default", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("unreviewed-toggle")).toBeInTheDocument();
    });
  });

  it("hide inactive toggle is present and active by default", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("hide-inactive-toggle")).toBeInTheDocument();
    });
  });

  it("toggling hide inactive off refetches with include_inactive", async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("account-row-acc-1")).toBeInTheDocument();
    });

    mockGetCashFlowSummary.mockClear();

    fireEvent.click(screen.getByTestId("hide-inactive-toggle"));

    await waitFor(() => {
      expect(mockGetCashFlowSummary).toHaveBeenCalledWith(
        expect.objectContaining({ include_inactive: true }),
      );
    });
  });

  it("hide net $0 toggle filters accounts with zero net flow", async () => {
    const summariesWithZero: CashFlowAccountSummary[] = [
      ...mockSummaries,
      {
        account_id: "acc-3",
        account_name: "Empty",
        total_inflows: "0",
        total_outflows: "0",
        net_flow: "0",
        activity_count: 0,
        unreviewed_count: 0,
      },
    ];
    mockGetCashFlowSummary.mockResolvedValue({ data: summariesWithZero });

    renderPage();
    await waitFor(() => {
      expect(screen.getByTestId("account-row-acc-3")).toBeInTheDocument();
    });

    // Toggle hide net $0
    fireEvent.click(screen.getByTestId("hide-zero-net-toggle"));

    await waitFor(() => {
      expect(screen.queryByTestId("account-row-acc-3")).not.toBeInTheDocument();
    });
    // Non-zero accounts remain
    expect(screen.getByTestId("account-row-acc-1")).toBeInTheDocument();
    expect(screen.getByTestId("account-row-acc-2")).toBeInTheDocument();
  });
});
