import {
  ArrowLeft,
  Download,
  File as FileIcon,
  Globe,
  Loader2,
  Lock,
  Trash2,
  Upload,
} from 'lucide-react';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { readableSize } from './size';
import {
  changeBucket,
  deleteBucket,
  deleteObject,
  fetchBucket,
  fetchObjects,
  uploadObject,
  type Bucket,
  type StoredObject,
} from './api';

/** One bucket: what it holds, and the way to put something else in it. */
export function BucketPage(): ReactNode {
  const { t, i18n } = useTranslation();
  const { name = '' } = useParams();
  const [bucket, setBucket] = useState<Bucket | null>(null);
  const [objects, setObjects] = useState<StoredObject[]>([]);
  const [prefix, setPrefix] = useState('');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchBucket(name, controller.signal),
      fetchObjects(name, { prefix }, controller.signal),
    ])
      .then(([found, held]) => {
        setBucket(found);
        setObjects(held);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, [name, prefix, reloads]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const upload = (files: FileList | null): void => {
    const file = files?.[0];
    if (!file) return;
    setBusy(true);
    setError(null);
    uploadObject(name, prefix + file.name, file)
      .then(reload)
      .catch(() => {
        setError(t('storage.error.upload'));
      })
      .finally(() => {
        setBusy(false);
        if (fileInput.current) fileInput.current.value = '';
      });
  };

  const drop = (key: string): void => {
    setBusy(true);
    deleteObject(name, key)
      .then(reload)
      .catch(() => {
        setError(t('storage.error.upload'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const toggleAccess = (): void => {
    if (bucket === null) return;
    setBusy(true);
    changeBucket(name, bucket.access === 'public' ? 'private' : 'public')
      .then(setBucket)
      .catch(() => {
        setError(t('storage.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const removeBucket = (): void => {
    setBusy(true);
    deleteBucket(name)
      .then(() => {
        window.location.assign('/storage');
      })
      .catch(() => {
        setError(t('storage.error.create'));
        setBusy(false);
      });
  };

  if (failed) {
    return (
      <div className="p-4 sm:p-6">
        <ErrorBanner message={t('storage.error.notFound')} />
      </div>
    );
  }

  if (bucket === null) {
    return (
      <p className="flex items-center gap-2 p-4 text-sm text-muted sm:p-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('storage.loading')}
      </p>
    );
  }

  const AccessIcon = bucket.access === 'public' ? Globe : Lock;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <Link to="/storage" className="flex items-center gap-2 text-sm text-muted hover:text-app">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {t('storage.backToList')}
      </Link>

      <div className="flex flex-wrap items-center gap-3">
        <h1 className="font-mono text-2xl font-semibold tracking-tight text-app">{bucket.name}</h1>
        <button
          type="button"
          onClick={toggleAccess}
          disabled={busy}
          className="flex items-center gap-1 rounded-full bg-surface-raised px-2.5 py-1 text-xs text-muted hover:text-app disabled:opacity-60"
        >
          <AccessIcon className="h-3 w-3" aria-hidden="true" />
          {t(bucket.access === 'public' ? 'storage.access.public' : 'storage.access.private')}
        </button>
        <span className="text-xs text-muted">
          {t('storage.objectCount', { count: bucket.objects })} · {readableSize(bucket.bytes)}
        </span>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-48 flex-1">
          <label htmlFor="objectPrefix" className="mb-1.5 block text-sm font-medium text-app">
            {t('storage.field.prefix')}
          </label>
          <input
            id="objectPrefix"
            type="text"
            value={prefix}
            onChange={(event) => {
              setPrefix(event.target.value);
            }}
            placeholder="zdjecia/lato/"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <label className="flex cursor-pointer items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover">
          <Upload className="h-4 w-4" aria-hidden="true" />
          {t('storage.upload')}
          <input
            ref={fileInput}
            type="file"
            className="sr-only"
            onChange={(event) => {
              upload(event.target.files);
            }}
          />
        </label>
      </div>

      {objects.length === 0 ? (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('storage.noObjects')}
        </p>
      ) : (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {objects.map((item) => (
            <li key={item.key} className="flex items-center gap-3 px-4 py-3">
              <FileIcon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm text-app">{item.key}</p>
                <p className="mt-0.5 truncate text-xs text-muted">
                  {readableSize(item.size)} · {item.contentType} ·{' '}
                  {new Date(item.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}
                </p>
              </div>
              <a
                href={item.url}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent"
                aria-label={t('storage.download', { key: item.key })}
              >
                <Download className="h-4 w-4" />
              </a>
              <button
                type="button"
                onClick={() => {
                  drop(item.key);
                }}
                disabled={busy}
                aria-label={t('storage.remove', { key: item.key })}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <button
        type="button"
        onClick={removeBucket}
        disabled={busy}
        className="flex items-center gap-2 rounded-lg border border-app bg-surface px-3 py-2 text-sm text-muted hover:text-error disabled:opacity-60"
      >
        <Trash2 className="h-4 w-4" aria-hidden="true" />
        {t('storage.deleteBucket')}
      </button>
    </div>
  );
}
