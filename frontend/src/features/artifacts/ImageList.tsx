import { Box, Copy, Loader2, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { readableSize } from '../storage/size';
import { fetchImages, removeImage, type Registry } from './api';

const SHORT_DIGEST = 19;

interface ImageListProps {
  project: Project;
  mayRemove: boolean;
}

/** The container images a project keeps, and how to reach them. */
export function ImageList({ project, mayRemove }: ImageListProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchImages(owner, slug, controller.signal)
      .then(setRegistry)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('artifacts.images.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, reloads, t]);

  const drop = (tag: string): void => {
    removeImage(owner, slug, tag)
      .then(() => {
        setReloads((count) => count + 1);
      })
      .catch(() => {
        setError(t('artifacts.images.error.load'));
      });
  };

  // The image address is the clone address without the scheme and the .git.
  const address = project.cloneUrl.replace(/^https?:\/\//, '').replace(/\.git$/, '');

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <p className="text-sm text-muted">{t('artifacts.images.description')}</p>
        {registry !== null && registry.blobs > 0 && (
          <p className="text-xs text-muted">
            {t('artifacts.images.usage', {
              blobs: registry.blobs,
              size: readableSize(registry.bytes),
            })}
          </p>
        )}
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {registry === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('artifacts.images.loading')}
        </p>
      )}

      {registry !== null && registry.images.length === 0 && (
        <div className="space-y-2 rounded-xl border border-app bg-surface px-4 py-6 text-center">
          <Box className="mx-auto h-6 w-6 text-muted" aria-hidden="true" />
          <p className="text-sm text-muted">{t('artifacts.images.empty')}</p>
          <code className="block font-mono text-xs text-muted">docker push {address}:1.0</code>
        </div>
      )}

      {registry !== null && registry.images.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {registry.images.map((image) => (
            <li key={image.tag} className="flex items-center gap-3 px-4 py-3">
              <Box className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm text-app">
                  {image.reference.split(':').slice(0, -1).join(':')}
                  <span className="text-accent">:{image.tag}</span>
                </p>
                <p className="mt-0.5 truncate font-mono text-xs text-muted">
                  {image.digest.slice(0, SHORT_DIGEST)}… · {readableSize(image.size)} ·{' '}
                  {new Date(image.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(`docker pull ${image.reference}`);
                }}
                aria-label={t('artifacts.images.copy', { tag: image.tag })}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent"
              >
                <Copy className="h-4 w-4" />
              </button>
              {mayRemove && (
                <button
                  type="button"
                  onClick={() => {
                    drop(image.tag);
                  }}
                  aria-label={t('artifacts.images.remove', { tag: image.tag })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
