import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { CopyButton } from '../../components/ui/CopyButton';
import type { Project } from './api';

/** What to type to get the first commit into a fresh repository. */
export function EmptyRepository({ project }: { project: Project }): ReactNode {
  const { t } = useTranslation();

  const firstPush = [
    'git init',
    `git remote add origin ${project.cloneUrl}`,
    'git add .',
    `git commit -m "${t('project.empty.firstCommit')}"`,
    `git push -u origin ${project.defaultBranch}`,
  ].join('\n');

  return (
    <div className="space-y-6 rounded-xl border border-app bg-surface p-4 shadow-app-sm sm:p-6">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
          {t('project.empty.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('project.empty.intro')}</p>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-app">{t('project.empty.cloneHeading')}</h3>
          <CopyButton value={project.cloneUrl} label={t('project.copyCloneUrl')} />
        </div>
        <pre className="overflow-x-auto rounded-lg bg-app p-3 font-mono text-xs text-app">
          git clone {project.cloneUrl}
        </pre>
      </div>

      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h3 className="text-sm font-medium text-app">{t('project.empty.pushHeading')}</h3>
          <CopyButton value={firstPush} label={t('project.empty.copyCommands')} />
        </div>
        <pre className="overflow-x-auto rounded-lg bg-app p-3 font-mono text-xs text-app">
          {firstPush}
        </pre>
      </div>

      <p className="text-xs text-muted">{t('project.empty.tokenHint')}</p>
    </div>
  );
}
