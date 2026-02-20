import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { AllocationTable } from "../../components/dashboard/AllocationTable";

const mockNavigate = vi.fn();

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockAllocations = [
  {
    asset_type_id: "at-1",
    asset_type_name: "US Stocks",
    asset_type_color: "#3B82F6",
    target_percent: "60.0",
    actual_percent: "55.0",
    delta_percent: "-5.0",
    value: "55000.00",
  },
  {
    asset_type_id: "at-2",
    asset_type_name: "Bonds",
    asset_type_color: "#10B981",
    target_percent: "40.0",
    actual_percent: "35.0",
    delta_percent: "-5.0",
    value: "35000.00",
  },
];

function renderTable(unassignedValue = "0", allocationTotal = "90000.00") {
  return render(
    <MemoryRouter>
      <AllocationTable allocations={mockAllocations} unassignedValue={unassignedValue} allocationTotal={allocationTotal} />
    </MemoryRouter>,
  );
}

describe("AllocationTable", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("clicking asset type row navigates to detail page", () => {
    renderTable();

    const stocksRow = screen.getByText("US Stocks").closest("tr")!;
    fireEvent.click(stocksRow);
    expect(mockNavigate).toHaveBeenCalledWith("/asset-types/at-1");
  });

  it("clicking another asset type row navigates correctly", () => {
    renderTable();

    const bondsRow = screen.getByText("Bonds").closest("tr")!;
    fireEvent.click(bondsRow);
    expect(mockNavigate).toHaveBeenCalledWith("/asset-types/at-2");
  });

  it("clicking Unknown row navigates to unassigned", () => {
    renderTable("10000.00");

    const unknownRow = screen.getByText("Unknown").closest("tr")!;
    fireEvent.click(unknownRow);
    expect(mockNavigate).toHaveBeenCalledWith("/asset-types/unassigned");
  });

  it("rows have cursor-pointer style", () => {
    renderTable("5000.00");

    const stocksRow = screen.getByText("US Stocks").closest("tr")!;
    expect(stocksRow.className).toContain("cursor-pointer");

    const unknownRow = screen.getByText("Unknown").closest("tr")!;
    expect(unknownRow.className).toContain("cursor-pointer");
  });

  it("renders total footer row with allocation total", () => {
    renderTable("0", "90000.00");

    expect(screen.getByText("Total")).toBeInTheDocument();
    // Check formatted value appears
    expect(screen.getByText("$90,000.00")).toBeInTheDocument();
  });

  it("renders total footer row with correct value when unassigned present", () => {
    renderTable("10000.00", "100000.00");

    expect(screen.getByText("Total")).toBeInTheDocument();
    expect(screen.getByText("$100,000.00")).toBeInTheDocument();
  });
});
