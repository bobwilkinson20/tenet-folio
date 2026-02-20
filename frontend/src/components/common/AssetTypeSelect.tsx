/**
 * Asset Type dropdown using Headless UI for a modern, polished look
 */

import { Listbox, ListboxButton, ListboxOption, ListboxOptions } from "@headlessui/react";
import { ChevronUpDownIcon, CheckIcon } from "@heroicons/react/20/solid";
import type { AssetType } from "@/types/assetType";

interface Props {
  value: string | null;
  onChange: (value: string | null) => void;
  assetTypes: AssetType[];
  disabled?: boolean;
  placeholder?: string;
}

export function AssetTypeSelect({
  value,
  onChange,
  assetTypes,
  disabled = false,
  placeholder = "Unknown",
}: Props) {
  const selected = assetTypes.find((t) => t.id === value);

  return (
    <Listbox value={value} onChange={onChange} disabled={disabled}>
      <ListboxButton className="relative w-full cursor-default rounded-md bg-tf-bg-surface py-1.5 pl-3 pr-10 text-left text-tf-text-primary ring-1 ring-inset ring-tf-border-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-tf-accent-primary sm:text-sm disabled:cursor-not-allowed disabled:bg-tf-bg-primary disabled:text-tf-text-tertiary">
        <span className="flex items-center gap-2">
          {selected?.color && (
            <span
              className="inline-block h-3 w-3 flex-shrink-0 rounded-full"
              style={{ backgroundColor: selected.color }}
            />
          )}
          <span className="block truncate">
            {selected?.name || placeholder}
          </span>
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
              {placeholder}
            </span>
            {!value && (
              <span className="absolute inset-y-0 right-0 flex items-center pr-4 text-tf-accent-primary group-data-[focus]:text-tf-text-primary">
                <CheckIcon className="h-5 w-5" aria-hidden="true" />
              </span>
            )}
          </ListboxOption>

          {assetTypes.map((type) => (
            <ListboxOption
              key={type.id}
              value={type.id}
              className="group relative cursor-default select-none py-2 pl-3 pr-9 text-tf-text-primary data-[focus]:bg-tf-accent-primary data-[focus]:text-tf-text-primary"
            >
              <div className="flex items-center gap-2">
                <span
                  className="inline-block h-3 w-3 flex-shrink-0 rounded-full"
                  style={{ backgroundColor: type.color }}
                />
                <span className="block truncate font-normal group-data-[selected]:font-semibold">
                  {type.name}
                </span>
              </div>
              {value === type.id && (
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
