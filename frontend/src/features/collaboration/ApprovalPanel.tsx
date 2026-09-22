import { Check, CircleCheck, CircleDashed, Undo2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { approveMergeRequest, revokeApproval, type ApprovalState } from './api';

interface ApprovalPanelProps {
  owner: string;
  slug: string;
  number: number;
  /** What the parent already read, so the merge button knows it too. */
  state: ApprovalState | null;
  /** The login of whoever is looking, or null for a visitor. */
  login: string | null;
  /** Nobody approves a request that is already merged or closed. */
  open: boolean;
  onChanged: () => void;
}

/** Who said yes, and whether that is enough to let the change in. */
export function ApprovalPanel({
  owner,
  slug,
  number,
  state,
  login,
  open,
  onChanged,
}: ApprovalPanelProps): ReactNode {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);

  const act = (action: () => Promise<ApprovalState>): void => {
    setBusy(true);
    action()
      .then(onChanged)
      .catch(onChanged)
      .finally(() => {
        setBusy(false);
      });
  };

  if (state === null) return null;
  // Nothing is asked for and nobody has said anything, so there is nothing to show.
  if (state.required === 0 && state.given.length === 0 && state.missingOwners.length === 0) {
    if (!open || login === null) return null;
  }

  const mine = state.given.find((given) => given.login === login) ?? null;

  return (
    <div className="space-y-2 rounded-lg border border-app bg-surface-raised p-3">
      <p className="flex items-center gap-2 text-sm text-app">
        {state.satisfied ? (
          <CircleCheck className="h-4 w-4 text-success" aria-hidden="true" />
        ) : (
          <CircleDashed className="h-4 w-4 text-warning" aria-hidden="true" />
        )}
        {state.required > 0
          ? t('approvals.counted', { counted: state.counted, required: state.required })
          : t('approvals.heading')}
      </p>

      {state.given.length > 0 && (
        <ul className="space-y-1">
          {state.given.map((given) => (
            <li key={given.login} className="flex items-center gap-2 text-xs">
              <Check
                className={`h-3 w-3 ${given.stale ? 'text-muted' : 'text-success'}`}
                aria-hidden="true"
              />
              <span className={given.stale ? 'text-muted line-through' : 'text-app'}>
                {given.displayName}
              </span>
              {given.stale && <span className="text-muted">{t('approvals.stale')}</span>}
            </li>
          ))}
        </ul>
      )}

      {state.missingOwners.length > 0 && (
        <p className="text-xs text-muted">
          {t('approvals.owners', { owners: state.missingOwners.join(', ') })}
        </p>
      )}

      {open && login !== null && (
        <button
          type="button"
          onClick={() => {
            act(() =>
              mine === null
                ? approveMergeRequest(owner, slug, number)
                : revokeApproval(owner, slug, number),
            );
          }}
          disabled={busy}
          className={
            mine === null
              ? 'flex w-full items-center justify-center gap-2 rounded-lg border border-app bg-surface px-3 py-2 text-sm font-medium text-app hover:bg-surface-raised disabled:opacity-60'
              : 'flex items-center gap-1.5 text-xs text-muted hover:text-app disabled:opacity-60'
          }
        >
          {mine === null ? (
            <>
              <Check className="h-4 w-4" aria-hidden="true" />
              {t('approvals.approve')}
            </>
          ) : (
            <>
              <Undo2 className="h-3 w-3" aria-hidden="true" />
              {t('approvals.revoke')}
            </>
          )}
        </button>
      )}
    </div>
  );
}
