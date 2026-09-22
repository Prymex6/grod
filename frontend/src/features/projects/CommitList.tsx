import { GitCommitHorizontal, Loader2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { fetchCommits, type Commit, type Project } from './api';

const COMMIT_LIMIT = 30;
const SHORT_HASH_LENGTH = 8;

/** History of one branch, newest first. */
export function CommitList({
  project,
  reference,
}: {
  project: Project;
  reference: string;
}): ReactNode {
  const { t, i18n } = useTranslation();
  const [commits, setCommits] = useState<Commit[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();

    fetchCommits(
      project.ownerLogin,
      project.slug,
      { ref: reference, limit: COMMIT_LIMIT },
      controller.signal,
    )
      .then(setCommits)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });

    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, reference]);

  return (
    <div className="space-y-3">
      {failed && <ErrorBanner message={t('project.error.commits')} />}

      {commits === null && !failed && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('project.loading')}
        </p>
      )}

      {commits !== null && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {commits.map((commit) => (
            <li key={commit.hash} className="flex items-start gap-3 px-4 py-3">
              <GitCommitHorizontal
                className="mt-0.5 h-4 w-4 shrink-0 text-muted"
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-app">{commit.subject}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {commit.authorName} ·{' '}
                  {new Date(commit.authoredAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}
                </p>
              </div>
              <code className="shrink-0 font-mono text-xs text-muted">
                {commit.hash.slice(0, SHORT_HASH_LENGTH)}
              </code>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
