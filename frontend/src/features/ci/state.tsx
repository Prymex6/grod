import { CircleCheck, CircleDashed, CircleSlash, CircleX, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { TranslationKey } from '../../i18n/keys';
import type { RunState } from './api';

export const STATE_ICON = {
  pending: CircleDashed,
  running: Loader2,
  success: CircleCheck,
  failed: CircleX,
  canceled: CircleSlash,
} as const satisfies Record<RunState, typeof CircleCheck>;

export const STATE_COLOUR = {
  pending: 'text-muted',
  running: 'text-info',
  success: 'text-success',
  failed: 'text-error',
  canceled: 'text-muted',
} as const satisfies Record<RunState, string>;

export const STATE_KEYS = {
  pending: 'ci.state.pending',
  running: 'ci.state.running',
  success: 'ci.state.success',
  failed: 'ci.state.failed',
  canceled: 'ci.state.canceled',
} as const satisfies Record<RunState, TranslationKey>;

/** How a pipeline or a job is doing, in one badge. */
export function StateBadge({ state }: { state: RunState }): ReactNode {
  const { t } = useTranslation();
  const Icon = STATE_ICON[state];
  return (
    <span
      className={`flex shrink-0 items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs font-medium ${STATE_COLOUR[state]}`}
    >
      <Icon className={`h-3 w-3 ${state === 'running' ? 'animate-spin' : ''}`} aria-hidden="true" />
      {t(STATE_KEYS[state])}
    </span>
  );
}
