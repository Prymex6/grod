import { GitBranch, Hammer, Loader2, Play } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import type { Project } from '../projects/api';
import { StateBadge } from './state';
import { fetchPipelines, startPipeline, type Pipeline } from './api';

const HTTP_NOT_FOUND = 404;
const SHORT_HASH = 8;

interface PipelineListProps {
  project: Project;
  reference: string;
  mayRun: boolean;
  onOpenPipeline: (number: number) => void;
}

/** Pipelines of a project, newest first, with a button to run one by hand. */
export function PipelineList({
  project,
  reference,
  mayRun,
  onOpenPipeline,
}: PipelineListProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [pipelines, setPipelines] = useState<Pipeline[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchPipelines(project.ownerLogin, project.slug, controller.signal)
      .then(setPipelines)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('ci.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, reloads, t]);

  const run = (): void => {
    setBusy(true);
    setError(null);
    startPipeline(project.ownerLogin, project.slug, reference)
      .then((pipeline) => {
        onOpenPipeline(pipeline.number);
      })
      .catch((cause: unknown) => {
        const missing = cause instanceof ApiError && cause.status === HTTP_NOT_FOUND;
        setError(t(missing ? 'ci.error.noConfig' : 'ci.error.start'));
      })
      .finally(() => {
        setBusy(false);
        setReloads((count) => count + 1);
      });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-muted">{t('ci.description')}</p>
        {mayRun && (
          <button
            type="button"
            onClick={run}
            disabled={busy}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            <Play className="h-4 w-4" aria-hidden="true" />
            {t('ci.run', { ref: reference })}
          </button>
        )}
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {pipelines === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('ci.loading')}
        </p>
      )}

      {pipelines !== null && pipelines.length === 0 && (
        <div className="space-y-2 rounded-xl border border-app bg-surface px-4 py-6 text-center">
          <Hammer className="mx-auto h-6 w-6 text-muted" aria-hidden="true" />
          <p className="text-sm text-muted">{t('ci.empty')}</p>
          <p className="font-mono text-xs text-muted">.grod/ci.yml</p>
        </div>
      )}

      {pipelines !== null && pipelines.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {pipelines.map((pipeline) => (
            <li key={pipeline.id}>
              <button
                type="button"
                onClick={() => {
                  onOpenPipeline(pipeline.number);
                }}
                className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-raised"
              >
                <span className="mt-0.5 shrink-0 font-mono text-xs text-muted">
                  #{pipeline.number}
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-app">
                    {pipeline.commitSubject || t('ci.noSubject')}
                  </p>
                  <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                    <span className="flex items-center gap-1">
                      <GitBranch className="h-3 w-3" aria-hidden="true" />
                      <span className="font-mono">{pipeline.ref}</span>
                    </span>
                    <span className="font-mono">{pipeline.commit.slice(0, SHORT_HASH)}</span>
                    <span>
                      {new Date(pipeline.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}
                    </span>
                    <span>{t('ci.jobCount', { count: pipeline.jobs.length })}</span>
                  </p>
                </div>
                <StateBadge state={pipeline.state} />
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
