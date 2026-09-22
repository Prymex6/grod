import type { ReactNode } from 'react';

import { LogoMark } from './LogoMark';

type LockupSize = 'sm' | 'md';

const MARK_SIZE: Record<LockupSize, string> = { sm: 'h-6 w-6', md: 'h-7 w-7' };
const TEXT_SIZE: Record<LockupSize, string> = { sm: 'text-base', md: 'text-lg' };

/** The mark next to the platform name. */
export function LogoLockup({ name, size = 'md' }: { name: string; size?: LockupSize }): ReactNode {
  return (
    <span className="inline-flex items-center gap-2 text-app">
      <span className="text-accent">
        <LogoMark className={MARK_SIZE[size]} />
      </span>
      <span className={`font-semibold tracking-tight ${TEXT_SIZE[size]}`}>{name}</span>
    </span>
  );
}
