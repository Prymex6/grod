import { ArrowLeft, CircleCheck, CircleDot, Loader2, Send, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import {
  addComment,
  changeIssue,
  fetchComments,
  fetchIssue,
  removeComment,
  type Comment,
  type Issue,
} from './api';

interface IssueDetailProps {
  project: Project;
  number: number;
  signedIn: boolean;
  onBack: () => void;
}

/** One issue with its discussion. */
export function IssueDetail({ project, number, signedIn, onBack }: IssueDetailProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [issue, setIssue] = useState<Issue | null>(null);
  const [comments, setComments] = useState<Comment[]>([]);
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const formatDate = (value: string): string =>
    new Date(value).toLocaleString(i18n.resolvedLanguage ?? 'pl');

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchIssue(project.ownerLogin, project.slug, number, controller.signal),
      fetchComments(project.ownerLogin, project.slug, number, controller.signal),
    ])
      .then(([found, discussion]) => {
        setIssue(found);
        setComments(discussion);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('issues.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, number, reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const toggleState = (): void => {
    if (issue === null) return;
    setBusy(true);
    setError(null);
    changeIssue(project.ownerLogin, project.slug, number, {
      state: issue.state === 'open' ? 'closed' : 'open',
    })
      .then(setIssue)
      .catch(() => {
        setError(t('issues.error.change'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const submitComment = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    addComment(project.ownerLogin, project.slug, number, body)
      .then(() => {
        setBody('');
        reload();
      })
      .catch(() => {
        setError(t('issues.error.comment'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (commentId: string): void => {
    setBusy(true);
    setError(null);
    removeComment(project.ownerLogin, project.slug, number, commentId)
      .then(reload)
      .catch(() => {
        setError(t('issues.error.change'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="space-y-5">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-sm font-medium text-accent hover:underline"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {t('issues.backToList')}
      </button>

      {error !== null && <ErrorBanner message={error} />}

      {issue === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('issues.loading')}
        </p>
      )}

      {issue !== null && (
        <>
          <div className="space-y-2">
            <h2 className="text-xl font-semibold tracking-tight text-app">
              {issue.title} <span className="font-mono text-muted">#{issue.number}</span>
            </h2>
            <div className="flex flex-wrap items-center gap-3">
              <span
                className={`flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                  issue.state === 'open'
                    ? 'bg-success-subtle text-success'
                    : 'bg-surface-raised text-muted'
                }`}
              >
                {issue.state === 'open' ? (
                  <CircleDot className="h-3.5 w-3.5" aria-hidden="true" />
                ) : (
                  <CircleCheck className="h-3.5 w-3.5" aria-hidden="true" />
                )}
                {issue.state === 'open' ? t('issues.state.open') : t('issues.state.closed')}
              </span>
              <p className="text-xs text-muted">
                {t('issues.openedBy', {
                  number: issue.number,
                  author: issue.author.displayName,
                  date: formatDate(issue.createdAt),
                })}
              </p>
              {signedIn && (
                <button
                  type="button"
                  onClick={toggleState}
                  disabled={busy}
                  className="ml-auto rounded-lg border border-app bg-app px-3 py-1.5 text-xs font-medium text-app hover:bg-surface-raised disabled:opacity-60"
                >
                  {issue.state === 'open' ? t('issues.close') : t('issues.reopen')}
                </button>
              )}
            </div>
          </div>

          {issue.description !== '' && (
            <div className="whitespace-pre-wrap rounded-xl border border-app bg-surface p-4 text-sm text-app shadow-app-sm">
              {issue.description}
            </div>
          )}

          <section aria-labelledby="discussion-heading" className="space-y-3">
            <h3
              id="discussion-heading"
              className="text-sm font-semibold uppercase tracking-wider text-muted"
            >
              {t('issues.discussion')}
            </h3>

            {comments.length === 0 ? (
              <p className="text-sm text-muted">{t('issues.noComments')}</p>
            ) : (
              <ul className="space-y-3">
                {comments.map((comment) => (
                  <li
                    key={comment.id}
                    className="rounded-xl border border-app bg-surface p-4 shadow-app-sm"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <p className="text-xs text-muted">
                        {comment.author.displayName} · {formatDate(comment.createdAt)}
                      </p>
                      {signedIn && (
                        <button
                          type="button"
                          onClick={() => {
                            drop(comment.id);
                          }}
                          disabled={busy}
                          aria-label={t('issues.removeComment')}
                          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      )}
                    </div>
                    <p className="mt-2 whitespace-pre-wrap text-sm text-app">{comment.body}</p>
                  </li>
                ))}
              </ul>
            )}

            {signedIn && (
              <form className="space-y-2" onSubmit={submitComment}>
                <label htmlFor="commentBody" className="sr-only">
                  {t('issues.commentLabel')}
                </label>
                <textarea
                  id="commentBody"
                  required
                  rows={3}
                  value={body}
                  onChange={(event) => {
                    setBody(event.target.value);
                  }}
                  placeholder={t('issues.commentPlaceholder')}
                  className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
                />
                <button
                  type="submit"
                  disabled={busy}
                  className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                >
                  <Send className="h-4 w-4" aria-hidden="true" />
                  {t('issues.comment')}
                </button>
              </form>
            )}
          </section>
        </>
      )}
    </div>
  );
}
