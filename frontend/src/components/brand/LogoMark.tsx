import type { ReactNode } from 'react';

/** Palisade with a gate — the Gród mark. Inherits colour from the parent. */
export function LogoMark({ className = 'h-7 w-7' }: { className?: string }): ReactNode {
  return (
    <svg
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path d="M4 28V12l2-3 2 3v16" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M10 28V12l2-3 2 3v16" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M20 28V12l2-3 2 3v16" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M26 28V12l2-3 2 3v16" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M14 20h4v8h-4z" stroke="currentColor" strokeWidth="2" strokeLinejoin="round" />
      <path d="M3 9h26" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
    </svg>
  );
}
