import { Compass, Loader2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ProjectList } from '../projects/ProjectList';
import { fetchPublicProjects, type Project } from '../projects/api';

/** Public projects of the whole instance, open to visitors without an account. */
export function ExplorePage(): ReactNode {
  const { t } = useTranslation();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchPublicProjects(controller.signal)
      .then(setProjects)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, []);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
          <Compass className="h-6 w-6 text-accent" aria-hidden="true" />
          {t('explore.title')}
        </h1>
        <p className="mt-1 text-sm text-muted">{t('explore.subtitle')}</p>
      </div>

      {failed && <ErrorBanner message={t('explore.error')} />}

      {projects === null && !failed && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('explore.loading')}
        </p>
      )}

      {projects !== null && projects.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('explore.empty')}
        </p>
      )}

      {projects !== null && projects.length > 0 && <ProjectList projects={projects} />}
    </div>
  );
}
