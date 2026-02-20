import type { ReactNode } from "react";

const MAX_WIDTH_CLASSES = {
  sm: "max-w-sm",
  md: "max-w-md",
  lg: "max-w-lg",
  xl: "max-w-xl",
} as const;

interface ModalProps {
  isOpen: boolean;
  onClose?: () => void;
  children: ReactNode;
  maxWidth?: "sm" | "md" | "lg" | "xl";
}

export function Modal({ isOpen, onClose, children, maxWidth = "md" }: ModalProps) {
  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 bg-tf-bg-overlay/50 flex items-center justify-center z-50"
      onClick={(e) => {
        if (e.target === e.currentTarget && onClose) onClose();
      }}
    >
      <div className={`bg-tf-bg-surface border border-tf-border-default rounded-lg p-6 w-full ${MAX_WIDTH_CLASSES[maxWidth]}`}>
        {children}
      </div>
    </div>
  );
}
