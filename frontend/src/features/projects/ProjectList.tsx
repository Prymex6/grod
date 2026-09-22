import { Building2, FolderGit2, Globe, Lock, Star } from 'lucide-react';
import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import type { TranslationKey } from '../../i18n/keys';
import type { Project, Visibility } from './api';

const VISIBILITY_ICON = {
  private: Lock,
  internal: Building2,
  public: Globe,
} as const satisfies Record<Visibility, typeof Lock>;

const VISIBILITY_KEY = {
  private: 'projects.visibility.private',
  internal: 'projects.visibility.internal',
  public: 'projects.visibility.public',
} as const satisfies Record<Visibility, TranslationKey>;

/** A list of projects, the same wherever the console shows one. */
export function ProjectList({ projects }: { projects: Project[] }): ReactNode {
  const { t } = useTranslation();

  return (
    <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
      {projects.map((project) => {
        const VisibilityIcon = VISIBILITY_ICON[project.visibility];
        return (
          <li key={project.id}>
            <Link
              to={`/${project.ownerLogin}/${project.slug}`}
              className="flex items-center gap-3 px-4 py-3 hover:bg-surface-raised"
            >
              <FolderGit2 className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2">
                  <span className="truncate font-mono text-sm font-medium text-accent">
                    {project.ownerLogin}/{project.slug}
                  </span>
                  <span className="flex items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                    <VisibilityIcon className="h-3 w-3" aria-hidden="true" />
                    {t(VISIBILITY_KEY[project.visibility])}
                  </span>
                </p>
                {project.description !== '' && (
                  <p className="mt-0.5 truncate text-xs text-muted">{project.description}</p>
                )}
              </div>
              {project.stars > 0 && (
                <span
                  className="flex shrink-0 items-center gap-1 text-xs text-muted"
                  aria-label={t('projects.starCount', { count: project.stars })}
                >
                  <Star className="h-3.5 w-3.5" aria-hidden="true" />
                  {project.stars}
                </span>
              )}
              {project.empty && (
                <span className="shrink-0 text-xs text-muted">{t('projects.emptyRepo')}</span>
              )}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}
