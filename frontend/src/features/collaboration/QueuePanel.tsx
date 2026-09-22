import { ListOrdered, Loader2, X } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import type { TranslationKey } from '../../i18n/keys';
import { enterQueue, fetchQueuePlace, leaveQueue, type QueuePlace } from './api';

const stateLabel = (state: QueuePlace['state']): TranslationKey =>
  `queue.state.${state}` as TranslationKey;

interface QueuePanelProps {
  owner: string;
  slug: string;
  number: number;
  /** Only somebody who may push decides what gets merged. */
  mayMerge: boolean;
  /** Standing in line makes sense only while the request is open. */
  open: boolean;
  onChanged: () => void;
}

/** Standing in line to be merged once the merge result passes its tests. */
export function QueuePanel({
  owner,
  slug,
  number,
  mayMerge,
  open,
  onChanged,
}: QueuePanelProps): ReactNode {
  const { t } = useTranslation();
  const [place, setPlace] = useState<QueuePlace | null>(null);
  const [busy, setBusy] = useState(false);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchQueuePlace(owner, slug, number, controller.signal)
      .then(setPlace)
      .catch(() => {
        // Nothing in line is the ordinary case, not a failure worth showing.
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, number, reloads]);

  const act = (action: () => Promise<unknown>): void => {
    setBusy(true);
    action()
      .then(() => {
        setReloads((count) => count + 1);
        onChanged();
      })
      .catch(() => {
        // Whatever went wrong shows up as the state the next read brings back.
        setReloads((count) => count + 1);
      })
      .finally(() => {
        setBusy(false);
      });
  };

  if (!open) return null;

  if (place === null) {
    if (!mayMerge) return null;
    return (
      <button
        type="button"
        onClick={() => {
          act(() => enterQueue(owner, slug, number));
        }}
        disabled={busy}
        className="flex w-full items-center justify-center gap-2 rounded-lg border border-app bg-surface-raised px-3 py-2 text-sm font-medium text-app hover:bg-surface disabled:opacity-60"
      >
        <ListOrdered className="h-4 w-4" aria-hidden="true" />
        {t('queue.enter')}
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-lg border border-app bg-surface-raised p-3">
      <p className="flex items-center gap-2 text-sm text-app">
        {place.state === 'testing' ? (
          <Loader2 className="h-4 w-4 animate-spin text-accent" aria-hidden="true" />
        ) : (
          <ListOrdered className="h-4 w-4 text-accent" aria-hidden="true" />
        )}
        {t(stateLabel(place.state))}
        {place.position > 0 && (
          <span className="ml-auto font-mono text-xs text-muted">
            {t('queue.position', { position: place.position })}
          </span>
        )}
      </p>

      <p className="text-xs text-muted">{t('queue.explains')}</p>

      {place.lastError !== '' && <p className="text-xs text-error">{place.lastError}</p>}

      {mayMerge && (
        <button
          type="button"
          onClick={() => {
            act(() => leaveQueue(owner, slug, number));
          }}
          disabled={busy}
          className="flex items-center gap-1.5 text-xs text-muted hover:text-app disabled:opacity-60"
        >
          <X className="h-3 w-3" aria-hidden="true" />
          {t('queue.leave')}
        </button>
      )}
    </div>
  );
}
