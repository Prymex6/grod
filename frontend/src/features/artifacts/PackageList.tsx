import { Download, Loader2, Package as PackageIcon, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { readableSize } from '../storage/size';
import { fetchPackages, removePackage, type Package } from './api';

interface PackageListProps {
  project: Project;
  mayRemove: boolean;
}

/** Files a project published, ready to download. */
export function PackageList({ project, mayRemove }: PackageListProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [packages, setPackages] = useState<Package[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchPackages(owner, slug, controller.signal)
      .then(setPackages)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('artifacts.packages.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, reloads, t]);

  const drop = (packageId: string): void => {
    removePackage(owner, slug, packageId)
      .then(() => {
        setReloads((count) => count + 1);
      })
      .catch(() => {
        setError(t('artifacts.packages.error.load'));
      });
  };

  return (
    <div className="space-y-4">
      <p className="text-sm text-muted">{t('artifacts.packages.description')}</p>

      {error !== null && <ErrorBanner message={error} />}

      {packages === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('artifacts.packages.loading')}
        </p>
      )}

      {packages !== null && packages.length === 0 && (
        <div className="space-y-2 rounded-xl border border-app bg-surface px-4 py-6 text-center">
          <PackageIcon className="mx-auto h-6 w-6 text-muted" aria-hidden="true" />
          <p className="text-sm text-muted">{t('artifacts.packages.empty')}</p>
          <code className="block font-mono text-xs text-muted">
            curl -X PUT --data-binary @plik.tar.gz &lt;adres&gt;/packages/nazwa/1.0.0/plik.tar.gz
          </code>
        </div>
      )}

      {packages !== null && packages.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {packages.map((item) => (
            <li key={item.id} className="flex items-center gap-3 px-4 py-3">
              <PackageIcon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate font-mono text-sm text-app">
                  {item.name} <span className="text-accent">{item.version}</span>
                </p>
                <p className="mt-0.5 truncate text-xs text-muted">
                  {item.filename} · {readableSize(item.size)} ·{' '}
                  {new Date(item.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}
                </p>
              </div>
              <a
                href={item.url}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent"
                aria-label={t('artifacts.packages.download', { filename: item.filename })}
              >
                <Download className="h-4 w-4" />
              </a>
              {mayRemove && (
                <button
                  type="button"
                  onClick={() => {
                    drop(item.id);
                  }}
                  aria-label={t('artifacts.packages.remove', { filename: item.filename })}
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
