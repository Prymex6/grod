import { ExternalLink, Globe, Loader2, Trash2, Upload } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import type { Project, Ref } from '../projects/api';
import { configureSite, fetchSite, publishSite, removeSite, type Site } from './api';

const HTTP_NOT_FOUND = 404;
const SHORT_HASH = 8;
const DIRECTORY_MAX_LENGTH = 500;

interface SiteSectionProps {
  project: Project;
  branches: Ref[];
}

/** The static site a project publishes from its repository. */
export function SiteSection({ project, branches }: SiteSectionProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [site, setSite] = useState<Site | null>(null);
  const [loading, setLoading] = useState(true);
  const [branch, setBranch] = useState(project.defaultBranch);
  const [directory, setDirectory] = useState('public');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchSite(owner, slug, controller.signal)
      .then((found) => {
        setSite(found);
        setBranch(found.branch);
        setDirectory(found.directory);
      })
      .catch((cause: unknown) => {
        // A project without a site answers 404; that is not an error here.
        const missing = cause instanceof ApiError && cause.status === HTTP_NOT_FOUND;
        if (!controller.signal.aborted && !missing) setError(t('pages.error.load'));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, t]);

  const save = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    configureSite(owner, slug, { branch, directory: directory.trim(), enabled: true })
      .then(setSite)
      .catch(() => {
        setError(t('pages.error.save'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const publish = (): void => {
    setBusy(true);
    setError(null);
    publishSite(owner, slug)
      .then(setSite)
      .catch((cause: unknown) => {
        const missing = cause instanceof ApiError && cause.status === HTTP_NOT_FOUND;
        setError(t(missing ? 'pages.error.nothing' : 'pages.error.publish'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const takeDown = (): void => {
    setBusy(true);
    setError(null);
    removeSite(owner, slug)
      .then(() => {
        setSite(null);
      })
      .catch(() => {
        setError(t('pages.error.save'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="site-heading" className="space-y-4">
      <div>
        <h2 id="site-heading" className="text-sm font-semibold uppercase tracking-wider text-muted">
          {t('pages.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('pages.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {loading && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('pages.loading')}
        </p>
      )}

      {!loading && site !== null && (
        <div className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
          <div className="flex flex-wrap items-center gap-2">
            <Globe className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
            <a
              href={site.url}
              target="_blank"
              rel="noreferrer"
              className="flex min-w-0 items-center gap-1 truncate font-mono text-sm text-accent hover:underline"
            >
              {site.url}
              <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
            </a>
          </div>
          <p className="text-xs text-muted">
            {site.publishedAt === null
              ? t('pages.neverPublished')
              : t('pages.publishedAt', {
                  date: new Date(site.publishedAt).toLocaleString(i18n.resolvedLanguage ?? 'pl'),
                  commit: (site.publishedCommit ?? '').slice(0, SHORT_HASH),
                })}
          </p>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={publish}
              disabled={busy}
              className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
            >
              <Upload className="h-4 w-4" aria-hidden="true" />
              {t('pages.publish')}
            </button>
            <button
              type="button"
              onClick={takeDown}
              disabled={busy}
              className="flex items-center gap-2 rounded-lg border border-app bg-surface-raised px-3 py-2 text-sm text-app hover:bg-surface hover:text-error disabled:opacity-60"
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
              {t('pages.takeDown')}
            </button>
          </div>
        </div>
      )}

      {!loading && (
        <form className="flex flex-wrap items-end gap-3" onSubmit={save}>
          <div className="min-w-40 flex-1">
            <label htmlFor="siteBranch" className="mb-1.5 block text-sm font-medium text-app">
              {t('pages.field.branch')}
            </label>
            <select
              id="siteBranch"
              value={branch}
              onChange={(event) => {
                setBranch(event.target.value);
              }}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app focus:border-accent focus:outline-none"
            >
              {branches.map((item) => (
                <option key={item.name} value={item.name}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-40 flex-1">
            <label htmlFor="siteDirectory" className="mb-1.5 block text-sm font-medium text-app">
              {t('pages.field.directory')}
            </label>
            <input
              id="siteDirectory"
              type="text"
              maxLength={DIRECTORY_MAX_LENGTH}
              value={directory}
              onChange={(event) => {
                setDirectory(event.target.value);
              }}
              placeholder="public"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
            <p className="mt-1 text-xs text-muted">{t('pages.field.directoryHint')}</p>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {site === null ? t('pages.setUp') : t('pages.save')}
          </button>
        </form>
      )}
    </section>
  );
}
