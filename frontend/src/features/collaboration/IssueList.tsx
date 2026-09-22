import { CircleCheck, CircleDot, Loader2, Plus } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { fetchIssues, openIssue, type Issue, type IssueState } from './api';

const FILTERS = ['open', 'closed', 'all'] as const;
type Filter = (typeof FILTERS)[number];

const FILTER_KEYS = {
  open: 'issues.filter.open',
  closed: 'issues.filter.closed',
  all: 'issues.filter.all',
} as const satisfies Record<Filter, string>;

const stateOf = (filter: Filter): IssueState | undefined => (filter === 'all' ? undefined : filter);

interface IssueListProps {
  project: Project;
  signedIn: boolean;
  onOpenIssue: (number: number) => void;
}

/** Issues of a project, with a filter and a form to open a new one. */
export function IssueList({ project, signedIn, onOpenIssue }: IssueListProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [filter, setFilter] = useState<Filter>('open');
  const [issues, setIssues] = useState<Issue[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchIssues(project.ownerLogin, project.slug, { state: stateOf(filter) }, controller.signal)
      .then(setIssues)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('issues.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, filter, reloads, t]);

  const submit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    openIssue(project.ownerLogin, project.slug, { title, description })
      .then((issue) => {
        setTitle('');
        setDescription('');
        setCreating(false);
        onOpenIssue(issue.number);
      })
      .catch(() => {
        setError(t('issues.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex gap-1 rounded-lg border border-app bg-surface p-1">
          {FILTERS.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => {
                setFilter(item);
                setIssues(null);
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

        {signedIn && (
          <button
            type="button"
            onClick={() => {
              setCreating((open) => !open);
            }}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('issues.new')}
          </button>
        )}
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={submit}
        >
          <div>
            <label htmlFor="issueTitle" className="mb-1.5 block text-sm font-medium text-app">
              {t('issues.field.title')}
            </label>
            <input
              id="issueTitle"
              type="text"
              required
              maxLength={200}
              value={title}
              onChange={(event) => {
                setTitle(event.target.value);
              }}
              placeholder={t('issues.field.titlePlaceholder')}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="issueBody" className="mb-1.5 block text-sm font-medium text-app">
              {t('issues.field.description')}
            </label>
            <textarea
              id="issueBody"
              rows={4}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              placeholder={t('issues.field.descriptionPlaceholder')}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {busy ? t('issues.creating') : t('issues.create')}
          </button>
        </form>
      )}

      {issues === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('issues.loading')}
        </p>
      )}

      {issues !== null && issues.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('issues.empty')}
        </p>
      )}

      {issues !== null && issues.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {issues.map((issue) => (
            <li key={issue.id}>
              <button
                type="button"
                onClick={() => {
                  onOpenIssue(issue.number);
                }}
                className="flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-surface-raised"
              >
                {issue.state === 'open' ? (
                  <CircleDot className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden="true" />
                ) : (
                  <CircleCheck className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-app">{issue.title}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    {t('issues.openedBy', {
                      number: issue.number,
                      author: issue.author.displayName,
                      date: new Date(issue.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl'),
                    })}
                  </p>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
