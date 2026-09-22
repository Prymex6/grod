import { Archive, Globe, Loader2, Lock, Plus } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import { readableSize } from './size';
import { createBucket, fetchBuckets, type Bucket, type BucketAccess } from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;

/** Buckets of the signed-in account, with a form to start a new one. */
export function StoragePage(): ReactNode {
  const { t } = useTranslation();
  const [buckets, setBuckets] = useState<Bucket[] | null>(null);
  const [name, setName] = useState('');
  const [access, setAccess] = useState<BucketAccess>('private');
  const [creating, setCreating] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchBuckets(controller.signal)
      .then(setBuckets)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('storage.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createBucket({ name: name.trim().toLowerCase(), access })
      .then(() => {
        setName('');
        setCreating(false);
        setReloads((count) => count + 1);
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'storage.error.taken' : 'storage.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <Archive className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('storage.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('storage.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('storage.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="flex flex-wrap items-end gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="min-w-48 flex-1">
            <label htmlFor="bucketName" className="mb-1.5 block text-sm font-medium text-app">
              {t('storage.field.name')}
            </label>
            <input
              id="bucketName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={name}
              onChange={(event) => {
                setName(event.target.value);
              }}
              placeholder="moje-pliki"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
            <p className="mt-1 text-xs text-muted">{t('storage.field.nameHint')}</p>
          </div>
          <div>
            <label htmlFor="bucketAccess" className="mb-1.5 block text-sm font-medium text-app">
              {t('storage.field.access')}
            </label>
            <select
              id="bucketAccess"
              value={access}
              onChange={(event) => {
                setAccess(event.target.value as BucketAccess);
              }}
              className="rounded-lg border border-app bg-surface px-2 py-2 text-sm text-app focus:border-accent focus:outline-none"
            >
              <option value="private">{t('storage.access.private')}</option>
              <option value="public">{t('storage.access.public')}</option>
            </select>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('storage.create')}
          </button>
        </form>
      )}

      {buckets === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('storage.loading')}
        </p>
      )}

      {buckets !== null && buckets.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('storage.empty')}
        </p>
      )}

      {buckets !== null && buckets.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {buckets.map((bucket) => {
            const AccessIcon = bucket.access === 'public' ? Globe : Lock;
            return (
              <li key={bucket.id}>
                <Link
                  to={`/storage/${bucket.name}`}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-surface-raised"
                >
                  <Archive className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="truncate font-mono text-sm font-medium text-accent">
                        {bucket.name}
                      </span>
                      <span className="flex items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                        <AccessIcon className="h-3 w-3" aria-hidden="true" />
                        {t(
                          bucket.access === 'public'
                            ? 'storage.access.public'
                            : 'storage.access.private',
                        )}
                      </span>
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      {t('storage.objectCount', { count: bucket.objects })} ·{' '}
                      {readableSize(bucket.bytes)}
                    </p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
