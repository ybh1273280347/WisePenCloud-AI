import type { ButtonHTMLAttributes, ReactNode } from "react";
import { cn } from "../../lib/utils";

type IconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  label: string;
  children: ReactNode;
};

export function IconButton({ className, label, children, ...props }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      className={cn(
        "inline-flex h-8 w-8 items-center justify-center rounded-lg border border-transparent tokenizer-gray-600 transition-colors hover:bg-sky-50 hover:tokenizer-sky-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500/25",
        className,
      )}
      type="button"
      {...props}
    >
      {children}
    </button>
  );
}
