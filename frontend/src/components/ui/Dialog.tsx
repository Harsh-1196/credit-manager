import React, { useEffect, useRef } from "react";
import { clsx } from "clsx";
import { twMerge } from "tailwind-merge";
import { Button } from "./Button";

export interface DialogProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children?: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  onConfirm?: () => void;
  isConfirmLoading?: boolean;
  isDestructive?: boolean;
  footer?: React.ReactNode;
}

export const Dialog: React.FC<DialogProps> = ({
  isOpen,
  onClose,
  title,
  description,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  isConfirmLoading = false,
  isDestructive = false,
  footer,
}) => {
  const dialogRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && isOpen) {
        onClose();
      }
    };
    if (isOpen) {
      document.body.style.overflow = "hidden";
      window.addEventListener("keydown", handleKeyDown);
    } else {
      document.body.style.overflow = "";
    }
    return () => {
      document.body.style.overflow = "";
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-ink/40 backdrop-blur-none"
      onClick={onClose}
      aria-modal="true"
      role="dialog"
      aria-labelledby="dialog-title"
      aria-describedby={description ? "dialog-desc" : undefined}
    >
      <div
        ref={dialogRef}
        onClick={(e) => e.stopPropagation()}
        className={twMerge(
          clsx(
            "w-full max-w-md rounded-lg bg-surface border border-border-strong p-6 shadow-overlay",
            "animate-in fade-in zoom-in-95 duration-150"
          )
        )}
      >
        <div className="flex flex-col gap-1 text-left">
          <h2 id="dialog-title" className="font-serif text-xl font-semibold text-ink">
            {title}
          </h2>
          {description && (
            <p id="dialog-desc" className="text-sm text-ink-muted">
              {description}
            </p>
          )}
        </div>

        {children && <div className="mt-4 text-sm text-ink">{children}</div>}

        {footer ? (
          <div className="mt-6">{footer}</div>
        ) : (
          <div className="mt-6 flex items-center justify-end gap-3">
            <Button variant="secondary" size="md" onClick={onClose} disabled={isConfirmLoading}>
              {cancelLabel}
            </Button>
            {onConfirm && (
              <Button
                variant={isDestructive ? "danger" : "primary"}
                size="md"
                onClick={onConfirm}
                isLoading={isConfirmLoading}
              >
                {confirmLabel}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
