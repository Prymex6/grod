import { Loader2, Plus } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ProjectList } from './ProjectList';
import { fetchProjects, fetchStarred, type Project } from './api';

const TABS = ['mine', 'starred'] as const;
type Tab = (typeof TABS)[number];

const TAB_KEYS = { mine: 'projects.tab.mine', starred: 'projects.tab.starred' } as const;

/** Projects of the signed-in account, and the ones it starred. */
export function ProjectsPage(): ReactNode {
  const { t } = useTranslation();
  const [tab, setTab] = useState<Tab>('mine');
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    const load = tab === 'mine' ? fetchProjects : fetchStarred;
    load(controller.signal)
      .then(setProjects)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, [tab]);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-app">{t('projects.title')}</h1>
          <p className="mt-1 text-sm text-muted">{t('projects.subtitle')}</p>
        </div>
        <Link
          to="/projects/new"
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('projects.create')}
        </Link>
      </div>

      <div className="flex gap-1 rounded-lg border border-app bg-surface p-1 w-fit">
        {TABS.map((item) => (
          <button
            key={item}
            type="button"
            onClick={() => {
              setTab(item);
              // The spinner comes back while the other listing loads.
              setProjects(null);
            }}
            aria-pressed={tab === item}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              tab === item
                ? 'bg-accent text-accent-contrast'
                : 'text-muted hover:bg-surface-raised hover:text-app'
            }`}
          >
            {t(TAB_KEYS[item])}
          </button>
        ))}
      </div>

      {failed && <ErrorBanner message={t('projects.error.load')} />}

      {projects === null && !failed && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('projects.loading')}
        </p>
      )}

      {projects !== null && projects.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t(tab === 'mine' ? 'projects.empty' : 'projects.noStars')}
        </p>
      )}

      {projects !== null && projects.length > 0 && <ProjectList projects={projects} />}
    </div>
  );
}
