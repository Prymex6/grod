import type { ReactNode } from 'react';

interface IconButtonProps {
  label: string;
  children: ReactNode;
  onClick?: () => void;
  expanded?: boolean;
  className?: string;
}

/** Square icon-only button; the label is what screen readers announce. */
export function IconButton({
  label,
  children,
  onClick,
  expanded,
  className = '',
}: IconButtonProps): ReactNode {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      aria-expanded={expanded}
      className={`flex h-9 w-9 items-center justify-center rounded-md text-muted transition-colors hover:bg-surface-raised hover:text-app ${className}`}
    >
      {children}
    </button>
  );
}
