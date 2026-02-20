/**
 * Tests for AssetTypeForm component
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { AssetTypeForm } from "@/components/settings/AssetTypeForm";
import { DEFAULT_COLORS } from "@/types/assetType";

vi.mock("@/api", () => ({
  assetTypeApi: {
    create: vi.fn(),
    update: vi.fn(),
  },
}));

import { assetTypeApi } from "@/api";

describe("AssetTypeForm", () => {
  const mockOnClose = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("rendering", () => {
    it("renders create form when no asset type provided", () => {
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      expect(screen.getByText("Add Asset Type")).toBeInTheDocument();
      expect(screen.getByPlaceholderText("e.g., US Equities")).toBeInTheDocument();
    });

    it("renders edit form when asset type provided", () => {
      const assetType = {
        id: "1",
        name: "Stocks",
        color: "#3B82F6",
        target_percent: 60,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
      };

      render(<AssetTypeForm assetType={assetType} onClose={mockOnClose} />);

      expect(screen.getByText("Edit Asset Type")).toBeInTheDocument();
      expect(screen.getByDisplayValue("Stocks")).toBeInTheDocument();
    });

    it("renders all predefined color options", () => {
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      // Should have 8 predefined color buttons + 1 custom button = 9 buttons in color section
      // Plus Cancel and Save buttons = 11 total, but we check color buttons specifically
      const colorButtons = document.querySelectorAll('button[type="button"]');
      // Filter out Cancel button (contains text) - color buttons have no text content
      const colorSwatches = Array.from(colorButtons).filter(
        (btn) => btn.textContent === "" && btn.getAttribute("aria-label") !== "Custom color"
      );
      expect(colorSwatches).toHaveLength(DEFAULT_COLORS.length);
    });

    it("renders custom color button", () => {
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      expect(screen.getByLabelText("Custom color")).toBeInTheDocument();
    });

    it("shows the selected color hex value", () => {
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      // Default color should be shown
      expect(screen.getByText(`Selected: ${DEFAULT_COLORS[0]}`)).toBeInTheDocument();
    });
  });

  describe("predefined color selection", () => {
    it("selects a predefined color when clicked", async () => {
      const user = userEvent.setup();
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      // Get all color swatch buttons (exclude Custom and Cancel buttons)
      const colorButtons = document.querySelectorAll('button[type="button"]');
      const colorSwatches = Array.from(colorButtons).filter(
        (btn) => btn.textContent === "" && btn.getAttribute("aria-label") !== "Custom color"
      );

      // Click the second color (green - index 1)
      const greenButton = colorSwatches[1];
      expect(greenButton).toBeInTheDocument();

      await user.click(greenButton);

      expect(screen.getByText(`Selected: ${DEFAULT_COLORS[1]}`)).toBeInTheDocument();
    });

    it("shows selection ring on selected predefined color", async () => {
      const user = userEvent.setup();
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      // Get all color swatch buttons (exclude Custom and Cancel buttons)
      const colorButtons = document.querySelectorAll('button[type="button"]');
      const colorSwatches = Array.from(colorButtons).filter(
        (btn) => btn.textContent === "" && btn.getAttribute("aria-label") !== "Custom color"
      );

      const greenButton = colorSwatches[1];
      await user.click(greenButton);

      expect(greenButton).toHaveClass("ring-2");
    });
  });

  describe("custom color selection", () => {
    it("shows color picker popover when custom button is clicked", async () => {
      const user = userEvent.setup();
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      const customButton = screen.getByLabelText("Custom color");
      await user.click(customButton);

      // react-colorful renders a color picker with specific class
      const colorPicker = document.querySelector(".react-colorful");
      expect(colorPicker).toBeInTheDocument();
    });

    it("hides color picker when custom button is clicked again", async () => {
      const user = userEvent.setup();
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      const customButton = screen.getByLabelText("Custom color");

      // Open
      await user.click(customButton);
      expect(document.querySelector(".react-colorful")).toBeInTheDocument();

      // Close
      await user.click(customButton);
      expect(document.querySelector(".react-colorful")).not.toBeInTheDocument();
    });

    it("shows selection state on custom button when custom color is active", async () => {
      const assetType = {
        id: "1",
        name: "Stocks",
        color: "#ff5500", // Not a default color
        target_percent: 60,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
      };

      render(<AssetTypeForm assetType={assetType} onClose={mockOnClose} />);

      const customButton = screen.getByLabelText("Custom color");
      expect(customButton).toHaveClass("ring-2");
    });

    it("does not show selection on custom button when predefined color is selected", () => {
      const assetType = {
        id: "1",
        name: "Stocks",
        color: DEFAULT_COLORS[0], // A default color
        target_percent: 60,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
      };

      render(<AssetTypeForm assetType={assetType} onClose={mockOnClose} />);

      const customButton = screen.getByLabelText("Custom color");
      expect(customButton).not.toHaveClass("ring-2");
    });

    it("closes color picker when predefined color is selected", async () => {
      const user = userEvent.setup();
      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      // Open color picker
      const customButton = screen.getByLabelText("Custom color");
      await user.click(customButton);
      expect(document.querySelector(".react-colorful")).toBeInTheDocument();

      // Click a predefined color
      const colorButtons = document.querySelectorAll('button[type="button"]');
      const colorSwatches = Array.from(colorButtons).filter(
        (btn) => btn.textContent === "" && btn.getAttribute("aria-label") !== "Custom color"
      );
      await user.click(colorSwatches[1]);

      // Color picker should be closed
      expect(document.querySelector(".react-colorful")).not.toBeInTheDocument();
    });
  });

  describe("form submission", () => {
    it("creates new asset type with selected color", async () => {
      const user = userEvent.setup();
      vi.mocked(assetTypeApi.create).mockResolvedValue({ data: {} } as never);

      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      // Fill in name
      const nameInput = screen.getByPlaceholderText("e.g., US Equities");
      await user.type(nameInput, "US Equities");

      // Select a color - get all color swatch buttons
      const colorButtons = document.querySelectorAll('button[type="button"]');
      const colorSwatches = Array.from(colorButtons).filter(
        (btn) => btn.textContent === "" && btn.getAttribute("aria-label") !== "Custom color"
      );
      const greenButton = colorSwatches[1];
      await user.click(greenButton);

      // Submit
      await user.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(assetTypeApi.create).toHaveBeenCalledWith({
          name: "US Equities",
          color: DEFAULT_COLORS[1],
        });
      });
    });

    it("saves asset type with custom color when editing", async () => {
      const user = userEvent.setup();
      vi.mocked(assetTypeApi.update).mockResolvedValue({ data: {} } as never);

      // Start with an asset type that has a custom color
      const assetType = {
        id: "1",
        name: "Custom Asset",
        color: "#abcdef", // Custom color
        target_percent: 0,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
      };

      render(<AssetTypeForm assetType={assetType} onClose={mockOnClose} />);

      // Submit without changes - should preserve custom color
      await user.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(assetTypeApi.update).toHaveBeenCalledWith("1", {
          name: "Custom Asset",
          color: "#abcdef",
        });
      });
    });

    it("updates existing asset type", async () => {
      const user = userEvent.setup();
      vi.mocked(assetTypeApi.update).mockResolvedValue({ data: {} } as never);

      const assetType = {
        id: "1",
        name: "Stocks",
        color: "#3B82F6",
        target_percent: 60,
        created_at: "2024-01-01",
        updated_at: "2024-01-01",
      };

      render(<AssetTypeForm assetType={assetType} onClose={mockOnClose} />);

      // Change name
      const nameInput = screen.getByDisplayValue("Stocks");
      await user.clear(nameInput);
      await user.type(nameInput, "US Stocks");

      // Submit
      await user.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(assetTypeApi.update).toHaveBeenCalledWith("1", {
          name: "US Stocks",
          color: "#3B82F6",
        });
      });
    });

    it("calls onClose after successful submission", async () => {
      const user = userEvent.setup();
      vi.mocked(assetTypeApi.create).mockResolvedValue({ data: {} } as never);

      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      const nameInput = screen.getByPlaceholderText("e.g., US Equities");
      await user.type(nameInput, "Test");

      await user.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(mockOnClose).toHaveBeenCalled();
      });
    });

    it("shows error when name is empty", async () => {
      const user = userEvent.setup();

      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      await user.click(screen.getByText("Save"));

      expect(screen.getByText("Name is required")).toBeInTheDocument();
      expect(assetTypeApi.create).not.toHaveBeenCalled();
    });

    it("shows error message on API failure", async () => {
      const user = userEvent.setup();
      vi.mocked(assetTypeApi.create).mockRejectedValue({
        response: { data: { detail: "Name already exists" } },
      });

      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      const nameInput = screen.getByPlaceholderText("e.g., US Equities");
      await user.type(nameInput, "Existing Name");

      await user.click(screen.getByText("Save"));

      await waitFor(() => {
        expect(screen.getByText("Name already exists")).toBeInTheDocument();
      });
    });
  });

  describe("cancel button", () => {
    it("calls onClose when cancel is clicked", async () => {
      const user = userEvent.setup();

      render(<AssetTypeForm assetType={null} onClose={mockOnClose} />);

      await user.click(screen.getByText("Cancel"));

      expect(mockOnClose).toHaveBeenCalled();
    });
  });
});
