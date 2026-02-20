import { Menu, MenuButton, MenuItem, MenuItems } from "@headlessui/react";
import { EllipsisVerticalIcon } from "@heroicons/react/20/solid";
import type { Account } from "@/types";

interface Props {
  account: Account;
  onEdit: (account: Account) => void;
  onToggleActive: (account: Account) => void;
  onDelete: (account: Account) => void;
}

export function AccountActionsMenu({
  account,
  onEdit,
  onToggleActive,
  onDelete,
}: Props) {
  return (
    <Menu as="div" className="relative inline-block text-left">
      <MenuButton
        className="p-1 rounded hover:bg-tf-bg-elevated"
        data-testid={`account-actions-${account.id}`}
      >
        <EllipsisVerticalIcon className="h-5 w-5 text-tf-text-tertiary" />
      </MenuButton>

      <MenuItems
        anchor="bottom end"
        className="z-50 mt-1 w-40 rounded-md bg-tf-bg-surface border border-tf-border-default focus-visible:outline-none [--anchor-gap:4px]"
      >
        <div className="py-1">
          <MenuItem>
            <button
              onClick={() => onEdit(account)}
              className="block w-full px-4 py-2 text-left text-sm text-tf-text-secondary data-[focus]:bg-tf-bg-elevated"
              data-testid={`edit-account-${account.id}`}
            >
              Edit
            </button>
          </MenuItem>
          <MenuItem>
            <button
              onClick={() => onToggleActive(account)}
              className="block w-full px-4 py-2 text-left text-sm text-tf-text-secondary data-[focus]:bg-tf-bg-elevated"
              data-testid={`toggle-active-${account.id}`}
            >
              {account.is_active ? "Deactivate" : "Activate"}
            </button>
          </MenuItem>
          <div className="border-t border-tf-border-subtle" />
          <MenuItem>
            <button
              onClick={() => onDelete(account)}
              className="block w-full px-4 py-2 text-left text-sm text-tf-negative data-[focus]:bg-tf-bg-elevated"
              data-testid={`delete-account-${account.id}`}
            >
              Delete
            </button>
          </MenuItem>
        </div>
      </MenuItems>
    </Menu>
  );
}
