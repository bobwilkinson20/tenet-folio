import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { AccountActionsMenu } from "../../components/accounts/AccountActionsMenu";
import type { Account } from "../../types";

const activeAccount: Account = {
  id: "acc-1",
  name: "Test Account",
  provider_name: "SnapTrade",
  institution_name: "Vanguard",
  external_id: "ext-1",
  is_active: true,
  account_type: null,
  include_in_allocation: true,
  assigned_asset_class_id: null,
  created_at: "2024-01-01T00:00:00Z",
  updated_at: "2024-01-01T00:00:00Z",
  value: "50000.00",
};

const inactiveAccount: Account = {
  ...activeAccount,
  id: "acc-2",
  is_active: false,
};

describe("AccountActionsMenu", () => {
  it("renders kebab menu button", () => {
    render(
      <AccountActionsMenu
        account={activeAccount}
        onEdit={vi.fn()}
        onToggleActive={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    expect(screen.getByTestId("account-actions-acc-1")).toBeInTheDocument();
  });

  it("shows Edit, Deactivate, and Delete items when menu is open", async () => {
    render(
      <AccountActionsMenu
        account={activeAccount}
        onEdit={vi.fn()}
        onToggleActive={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("account-actions-acc-1"));

    expect(await screen.findByText("Edit")).toBeInTheDocument();
    expect(screen.getByText("Deactivate")).toBeInTheDocument();
    expect(screen.getByText("Delete")).toBeInTheDocument();
  });

  it("shows Activate for inactive accounts", async () => {
    render(
      <AccountActionsMenu
        account={inactiveAccount}
        onEdit={vi.fn()}
        onToggleActive={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("account-actions-acc-2"));

    expect(await screen.findByText("Activate")).toBeInTheDocument();
  });

  it("calls onEdit when Edit is clicked", async () => {
    const onEdit = vi.fn();
    render(
      <AccountActionsMenu
        account={activeAccount}
        onEdit={onEdit}
        onToggleActive={vi.fn()}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("account-actions-acc-1"));
    fireEvent.click(await screen.findByText("Edit"));

    expect(onEdit).toHaveBeenCalledWith(activeAccount);
  });

  it("calls onToggleActive when Deactivate is clicked", async () => {
    const onToggleActive = vi.fn();
    render(
      <AccountActionsMenu
        account={activeAccount}
        onEdit={vi.fn()}
        onToggleActive={onToggleActive}
        onDelete={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByTestId("account-actions-acc-1"));
    fireEvent.click(await screen.findByText("Deactivate"));

    expect(onToggleActive).toHaveBeenCalledWith(activeAccount);
  });

  it("calls onDelete when Delete is clicked", async () => {
    const onDelete = vi.fn();
    render(
      <AccountActionsMenu
        account={activeAccount}
        onEdit={vi.fn()}
        onToggleActive={vi.fn()}
        onDelete={onDelete}
      />,
    );

    fireEvent.click(screen.getByTestId("account-actions-acc-1"));
    fireEvent.click(await screen.findByText("Delete"));

    expect(onDelete).toHaveBeenCalledWith(activeAccount);
  });
});
