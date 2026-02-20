/**
 * Account Type dropdown using Headless UI for a modern, polished look.
 * Matches the style of AssetTypeSelect.
 */

import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { ChevronUpDownIcon, CheckIcon } from "@heroicons/react/20/solid";
import type { AccountType } from "@/types";
import { ACCOUNT_TYPE_LABELS } from "@/types";

const ACCOUNT_TYPE_OPTIONS: { value: AccountType; label: string }[] =
  (Object.entries(ACCOUNT_TYPE_LABELS) as [AccountType, string][]).map(
    ([value, label]) => ({ value, label }),
  );

interface Props {
  value: AccountType | null;
  onChange: (value: AccountType | null) => void;
  disabled?: boolean;
}

export function AccountTypeSelect({
  value,
  onChange,
  disabled = false,
}: Props) {
  const selected = ACCOUNT_TYPE_OPTIONS.find((opt) => opt.value === value);

  return (
    <Listbox value={value} onChange={onChange} disabled={disabled}>
      <ListboxButton
        className="relative w-full cursor-default rounded-md bg-tf-bg-surface py-1.5 pl-3 pr-10 text-left text-tf-text-primary ring-1 ring-inset ring-tf-border-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary sm:text-sm disabled:cursor-not-allowed disabled:bg-tf-bg-primary disabled:text-tf-text-tertiary"
        data-testid="edit-account-type"
      >
        <span className="block truncate">
          {selected?.label || "None"}
        </span>
        <span className="pointer-events-none absolute inset-y-0 right-0 flex items-center pr-2">
          <ChevronUpDownIcon
            className="h-5 w-5 text-tf-text-tertiary"
            aria-hidden="true"
          />
        </span>
      </ListboxButton>

      <ListboxOptions
        anchor="bottom"
        className="z-50 mt-1 max-h-60 w-[var(--button-width)] overflow-auto rounded-md bg-tf-bg-surface py-1 text-base border border-tf-border-default focus-visible:outline-none sm:text-sm [--anchor-gap:4px]"
      >
        <ListboxOption
          value={null}
          className="group relative cursor-default select-none py-2 pl-3 pr-9 text-tf-text-primary data-[focus]:bg-tf-accent-primary data-[focus]:text-tf-text-primary"
        >
          <span className="block truncate font-normal group-data-[selected]:font-semibold">
            None
          </span>
          {!value && (
            <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-tf-accent-primary group-data-[focus]:text-tf-text-primary">
              <CheckIcon className="h-5 w-5" aria-hidden="true" />
            </span>
          )}
        </ListboxOption>

        {ACCOUNT_TYPE_OPTIONS.map((opt) => (
          <ListboxOption
            key={opt.value}
            value={opt.value}
            className="group relative cursor-default select-none py-2 pl-3 pr-9 text-tf-text-primary data-[focus]:bg-tf-accent-primary data-[focus]:text-tf-text-primary"
          >
            <span className="block truncate font-normal group-data-[selected]:font-semibold">
              {opt.label}
            </span>
            {value === opt.value && (
              <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-tf-accent-primary group-data-[focus]:text-tf-text-primary">
                <CheckIcon className="h-5 w-5" aria-hidden="true" />
              </span>
            )}
          </ListboxOption>
        ))}
      </ListboxOptions>
    </Listbox>
  );
}
