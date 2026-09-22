import { ArrowLeft, GitBranch, Loader2, Square } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { STATE_COLOUR, STATE_ICON, StateBadge } from './state';
import { cancelPipeline, fetchJobLog, fetchPipeline, type Job, type Pipeline } from './api';

const SHORT_HASH = 8;
// While something still runs, the console asks again every few seconds.
const REFRESH_MS = 3000;

const isRunning = (pipeline: Pipeline): boolean =>
  pipeline.state === 'pending' || pipeline.state === 'running';

interface PipelineDetailProps {
  project: Project;
  number: number;
  mayRun: boolean;
  onBack: () => void;
}

/** One pipeline: its jobs, grouped by stage, and the log of the chosen job. */
export function PipelineDetail({
  project,
  number,
  mayRun,
  onBack,
}: PipelineDetailProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [pipeline, setPipeline] = useState<Pipeline | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [log, setLog] = useState('');
  const [failed, setFailed] = useState(false);
  const [ticks, setTicks] = useState(0);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchPipeline(owner, slug, number, controller.signal)
      .then((found) => {
        setPipeline(found);
        setJobId((current) => current ?? found.jobs[0]?.id ?? null);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, number, ticks]);

  useEffect(() => {
    if (jobId === null) return undefined;
    const controller = new AbortController();
    fetchJobLog(owner, slug, jobId, controller.signal)
      .then((found) => {
        setLog(found.log);
      })
      .catch(() => {
        // An empty log is the honest answer when it cannot be read.
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, jobId, ticks]);

  useEffect(() => {
    if (pipeline === null || !isRunning(pipeline)) return undefined;
    const timer = setInterval(() => {
      setTicks((count) => count + 1);
    }, REFRESH_MS);
    return () => {
      clearInterval(timer);
    };
  }, [pipeline]);

  if (failed) return <ErrorBanner message={t('ci.error.notFound')} />;

  if (pipeline === null) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('ci.loading')}
      </p>
    );
  }

  const stages = [...new Set(pipeline.jobs.map((job) => job.stage))];
  const chosen = pipeline.jobs.find((job) => job.id === jobId) ?? null;

  const stop = (): void => {
    void cancelPipeline(owner, slug, number).then(setPipeline);
  };

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-muted hover:text-app"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {t('ci.backToList')}
      </button>

      <div className="rounded-xl border border-app bg-surface p-4 shadow-app-sm">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="min-w-0 flex-1 text-lg font-semibold text-app">
            #{pipeline.number} {pipeline.commitSubject}
          </h1>
          <StateBadge state={pipeline.state} />
          {mayRun && isRunning(pipeline) && (
            <button
              type="button"
              onClick={stop}
              className="flex items-center gap-1.5 rounded-lg border border-app bg-surface-raised px-2.5 py-1.5 text-sm text-app hover:bg-surface"
            >
              <Square className="h-3.5 w-3.5" aria-hidden="true" />
              {t('ci.cancel')}
            </button>
          )}
        </div>
        <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
          <span className="flex items-center gap-1">
            <GitBranch className="h-3 w-3" aria-hidden="true" />
            <span className="font-mono">{pipeline.ref}</span>
          </span>
          <span className="font-mono">{pipeline.commit.slice(0, SHORT_HASH)}</span>
          <span>{new Date(pipeline.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}</span>
        </p>
      </div>

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="w-full shrink-0 space-y-3 lg:w-64">
          {stages.map((stage) => (
            <section key={stage} className="space-y-1.5">
              <h2 className="text-xs font-semibold uppercase tracking-wider text-muted">{stage}</h2>
              <ul className="space-y-1.5">
                {pipeline.jobs
                  .filter((job) => job.stage === stage)
                  .map((job) => (
                    <li key={job.id}>
                      <JobButton
                        job={job}
                        chosen={job.id === jobId}
                        onChoose={() => {
                          setJobId(job.id);
                        }}
                      />
                    </li>
                  ))}
              </ul>
            </section>
          ))}
        </div>

        <div className="min-w-0 flex-1 overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          <div className="flex items-center gap-2 border-b border-app bg-surface-raised px-3 py-2">
            <span className="min-w-0 flex-1 truncate font-mono text-xs text-app">
              {chosen?.name ?? ''}
            </span>
            {chosen !== null && <StateBadge state={chosen.state} />}
          </div>
          <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap break-words bg-app p-3 font-mono text-xs text-app">
            {log || t('ci.noLog')}
          </pre>
        </div>
      </div>
    </div>
  );
}

interface JobButtonProps {
  job: Job;
  chosen: boolean;
  onChoose: () => void;
}

/** One job in the list beside the log. */
function JobButton({ job, chosen, onChoose }: JobButtonProps): ReactNode {
  const Icon = STATE_ICON[job.state];
  return (
    <button
      type="button"
      onClick={onChoose}
      aria-pressed={chosen}
      className={`flex w-full items-center gap-2 rounded-lg border px-2.5 py-2 text-left text-sm ${
        chosen
          ? 'border-accent bg-accent-subtle text-app'
          : 'border-app bg-surface text-muted hover:bg-surface-raised'
      }`}
    >
      <Icon
        className={`h-4 w-4 shrink-0 ${STATE_COLOUR[job.state]} ${
          job.state === 'running' ? 'animate-spin' : ''
        }`}
        aria-hidden="true"
      />
      <span className="min-w-0 flex-1 truncate">{job.name}</span>
    </button>
  );
}
