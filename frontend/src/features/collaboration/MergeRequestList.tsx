import { GitMerge, GitPullRequest, GitPullRequestClosed, Loader2, Plus } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import type { Project, Ref } from '../projects/api';
import { fetchMergeRequests, openMergeRequest, type MergeRequest, type MergeState } from './api';

const FILTERS = ['open', 'merged', 'closed', 'all'] as const;
type Filter = (typeof FILTERS)[number];

const HTTP_UNPROCESSABLE = 422;
const TITLE_MAX_LENGTH = 200;

const FILTER_KEYS = {
  open: 'merges.filter.open',
  merged: 'merges.filter.merged',
  closed: 'merges.filter.closed',
  all: 'merges.filter.all',
} as const satisfies Record<Filter, TranslationKey>;

export const STATE_ICON = {
  open: GitPullRequest,
  merged: GitMerge,
  closed: GitPullRequestClosed,
} as const satisfies Record<MergeState, typeof GitMerge>;

export const STATE_COLOUR = {
  open: 'text-success',
  merged: 'text-accent',
  closed: 'text-muted',
} as const satisfies Record<MergeState, string>;

export const STATE_KEYS = {
  open: 'merges.state.open',
  merged: 'merges.state.merged',
  closed: 'merges.state.closed',
} as const satisfies Record<MergeState, TranslationKey>;

const stateOf = (filter: Filter): MergeState | undefined => (filter === 'all' ? undefined : filter);

/** The pair of branches a request moves code between. */
export function BranchPair({ from, to }: { from: string; to: string }): ReactNode {
  return (
    <span className="flex min-w-0 items-center gap-1 font-mono text-xs text-muted">
      <span className="truncate rounded bg-surface-raised px-1.5 py-0.5">{from}</span>
      <span aria-hidden="true">→</span>
      <span className="truncate rounded bg-surface-raised px-1.5 py-0.5">{to}</span>
    </span>
  );
}

/** The badge every view uses to show where a request stands. */
export function StateBadge({ state }: { state: MergeState }): ReactNode {
  const { t } = useTranslation();
  const Icon = STATE_ICON[state];
  return (
    <span
      className={`flex shrink-0 items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs font-medium ${STATE_COLOUR[state]}`}
    >
      <Icon className="h-3 w-3" aria-hidden="true" />
      {t(STATE_KEYS[state])}
    </span>
  );
}

interface MergeRequestListProps {
  project: Project;
  branches: Ref[];
  mayOpen: boolean;
  onOpenRequest: (number: number) => void;
}

/** Merge requests of a project, with a filter and a form to open a new one. */
export function MergeRequestList({
  project,
  branches,
  mayOpen,
  onOpenRequest,
}: MergeRequestListProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState<Filter>('open');
  const [requests, setRequests] = useState<MergeRequest[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [source, setSource] = useState('');
  const [target, setTarget] = useState(project.defaultBranch);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchMergeRequests(
      project.ownerLogin,
      project.slug,
      { state: stateOf(filter) },
      controller.signal,
    )
      .then(setRequests)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('merges.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, filter, reloads, t]);

  const submit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    openMergeRequest(project.ownerLogin, project.slug, {
      title,
      description,
      sourceBranch: source,
      targetBranch: target,
    })
      .then((request) => {
        setTitle('');
        setDescription('');
        setCreating(false);
        onOpenRequest(request.number);
      })
      .catch((cause: unknown) => {
        const sameBranch = cause instanceof ApiError && cause.status === HTTP_UNPROCESSABLE;
        setError(t(sameBranch ? 'merges.error.sameBranch' : 'merges.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const branchOptions = branches.map((branch) => (
    <option key={branch.name} value={branch.name}>
      {branch.name}
    </option>
  ));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-wrap gap-1 rounded-lg border border-app bg-surface p-1">
          {FILTERS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => {
                setFilter(item);
                setRequests(null);
                setReloads((count) => count + 1);
              }}
              aria-pressed={filter === item}
              className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                filter === item
                  ? 'bg-accent text-accent-contrast'
                  : 'text-muted hover:bg-surface-raised hover:text-app'
              }`}
            >
              {t(FILTER_KEYS[item])}
            </button>
          ))}
        </div>

        {mayOpen && (
          <button
            type="button"
            onClick={() => {
              setCreating((open) => !open);
              setSource((current) => (current === '' ? (branches[0]?.name ?? '') : current));
            }}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('merges.new')}
          </button>
        )}
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={submit}
        >
          <div className="flex flex-wrap gap-3">
            <div className="min-w-40 flex-1">
              <label htmlFor="mergeSource" className="mb-1.5 block text-sm font-medium text-app">
                {t('merges.field.source')}
              </label>
              <select
                id="mergeSource"
                value={source}
                onChange={(event) => {
                  setSource(event.target.value);
                }}
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app focus:border-accent focus:outline-none"
              >
                {branchOptions}
              </select>
            </div>
            <div className="min-w-40 flex-1">
              <label htmlFor="mergeTarget" className="mb-1.5 block text-sm font-medium text-app">
                {t('merges.field.target')}
              </label>
              <select
                id="mergeTarget"
                value={target}
                onChange={(event) => {
                  setTarget(event.target.value);
                }}
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app focus:border-accent focus:outline-none"
              >
                {branchOptions}
              </select>
            </div>
          </div>
          <div>
            <label htmlFor="mergeTitle" className="mb-1.5 block text-sm font-medium text-app">
              {t('merges.field.title')}
            </label>
            <input
              id="mergeTitle"
              type="text"
              required
              maxLength={TITLE_MAX_LENGTH}
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
              }}
              placeholder={t('merges.field.titlePlaceholder')}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="mergeBody" className="mb-1.5 block text-sm font-medium text-app">
              {t('merges.field.description')}
            </label>
            <textarea
              id="mergeBody"
              rows={3}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              placeholder={t('merges.field.descriptionPlaceholder')}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {busy ? t('merges.creating') : t('merges.create')}
          </button>
        </form>
      )}

      {requests === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('merges.loading')}
        </p>
      )}

      {requests !== null && requests.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('merges.empty')}
        </p>
      )}

      {requests !== null && requests.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {requests.map((request) => {
            const Icon = STATE_ICON[request.state];
            return (
              <li key={request.id}>
                <button
                  type="button"
                  onClick={() => {
                    onOpenRequest(request.number);
                  }}
                  className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-raised"
                >
                  <Icon
                    className={`mt-0.5 h-4 w-4 shrink-0 ${STATE_COLOUR[request.state]}`}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm text-app">{request.title}</p>
                    <p className="mt-0.5 text-xs text-muted">
                      {t('merges.openedBy', {
                        number: request.number,
                        author: request.author.displayName,
                        date: new Date(request.createdAt).toLocaleString(
                          i18n.resolvedLanguage ?? 'pl',
                        ),
                      })}
                    </p>
                    <div className="mt-1">
                      <BranchPair from={request.sourceBranch} to={request.targetBranch} />
                    </div>
                  </div>
                  <StateBadge state={request.state} />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
