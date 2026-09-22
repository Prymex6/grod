import { AlertTriangle, ArrowLeft, CheckCircle2, GitCommitHorizontal, Loader2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import type { Project } from '../projects/api';
import { ApprovalPanel } from './ApprovalPanel';
import { StackPanel } from './StackPanel';
import { DiffView } from './DiffView';
import { QueuePanel } from './QueuePanel';
import { BranchPair, StateBadge } from './MergeRequestList';
import {
  addReviewComment,
  closeMergeRequest,
  fetchChanges,
  fetchMergeCommits,
  fetchMergeRequest,
  fetchReviewComments,
  applySuggestion,
  fetchApprovals,
  fetchFindings,
  mergeMergeRequest,
  removeReviewComment,
  reopenMergeRequest,
  type FileChange,
  type MergeCommit,
  type MergeRequest,
  type ReviewComment,
  type ApprovalState,
  type Finding,
} from './api';

const TABS = ['discussion', 'commits', 'changes'] as const;
type Tab = (typeof TABS)[number];

const TAB_KEYS = {
  discussion: 'merges.tab.discussion',
  commits: 'merges.tab.commits',
  changes: 'merges.tab.changes',
} as const satisfies Record<Tab, TranslationKey>;

/** Read the conflicting paths the API reports when a merge is refused. */
const conflictsOf = (cause: unknown): string[] => {
  if (!(cause instanceof ApiError)) return [];
  const { detail } = cause;
  if (typeof detail !== 'object' || detail === null || !('conflicts' in detail)) return [];
  const { conflicts: listed } = detail;
  if (!Array.isArray(listed)) return [];
  return listed.filter((item): item is string => typeof item === 'string');
};

interface MergePanelProps {
  request: MergeRequest;
  conflicts: string[];
  mayMerge: boolean;
  mayChange: boolean;
  busy: boolean;
  /** The approval and queue panels, shown above the buttons. */
  approvals: ReactNode;
  queue: ReactNode;
  /** The stack this request belongs to, when it stands in one. */
  stack: ReactNode;
  /** False when the request still waits for somebody to say yes. */
  approved: boolean;
  onMerge: () => void;
  onClose: () => void;
  onReopen: () => void;
}

/** The panel that says whether the branches merge, and does it. */
function MergePanel({
  request,
  conflicts,
  mayMerge,
  mayChange,
  busy,
  approvals,
  queue,
  stack,
  approved,
  onMerge,
  onClose,
  onReopen,
}: MergePanelProps): ReactNode {
  const { t, i18n } = useTranslation();
  const formatDate = (value: string): string =>
    new Date(value).toLocaleString(i18n.resolvedLanguage ?? 'pl');

  return (
    <aside
      aria-label={t('merges.panel.title')}
      className="flex w-full shrink-0 flex-col gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm lg:w-80"
    >
      <h2 className="text-sm font-semibold uppercase tracking-wider text-muted">
        {t('merges.panel.title')}
      </h2>

      {request.state === 'merged' && request.mergedAt !== null && (
        <p className="text-sm text-muted">
          {t('merges.mergedAs', {
            date: formatDate(request.mergedAt),
            commit: (request.mergeCommit ?? '').slice(0, 8),
          })}
        </p>
      )}

      {request.state === 'closed' && request.closedAt !== null && (
        <p className="text-sm text-muted">
          {t('merges.closedAt', { date: formatDate(request.closedAt) })}
        </p>
      )}

      {request.state === 'open' && conflicts.length === 0 && (
        <p className="flex items-start gap-2 text-sm text-success">
          <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          {t('merges.panel.ready')}
        </p>
      )}

      {request.state === 'open' && conflicts.length > 0 && (
        <div className="flex flex-col gap-2 text-sm">
          <p className="flex items-start gap-2 font-medium text-warning">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
            {t('merges.conflict.heading')}
          </p>
          <p className="text-muted">{t('merges.conflict.description')}</p>
          <p className="text-xs font-medium text-muted">{t('merges.conflict.files')}</p>
          <ul className="flex flex-col gap-1">
            {conflicts.map((path) => (
              <li
                key={path}
                className="truncate rounded-lg bg-surface-raised px-2 py-1 font-mono text-xs text-app"
              >
                {path}
              </li>
            ))}
          </ul>
        </div>
      )}

      {stack}

      {approvals}

      {request.state === 'open' && queue}

      <div className="mt-auto flex flex-wrap gap-2">
        {request.state === 'open' && mayMerge && (
          <button
            type="button"
            onClick={onMerge}
            disabled={busy || conflicts.length > 0 || !approved}
            className="flex-1 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
          >
            {busy ? t('merges.merging') : t('merges.merge')}
          </button>
        )}
        {request.state === 'open' && mayChange && (
          <button
            type="button"
            onClick={onClose}
            disabled={busy}
            className="flex-1 rounded-lg border border-app bg-surface-raised px-3 py-2 text-sm font-medium text-app hover:bg-surface disabled:opacity-60"
          >
            {t('merges.close')}
          </button>
        )}
        {request.state === 'closed' && mayChange && (
          <button
            type="button"
            onClick={onReopen}
            disabled={busy}
            className="flex-1 rounded-lg border border-app bg-surface-raised px-3 py-2 text-sm font-medium text-app hover:bg-surface disabled:opacity-60"
          >
            {t('merges.reopen')}
          </button>
        )}
      </div>
    </aside>
  );
}

/** The list of commits the source branch brings in. */
function CommitTab({ commits }: { commits: MergeCommit[] }): ReactNode {
  const { t, i18n } = useTranslation();
  if (commits.length === 0) {
    return (
      <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
        {t('merges.commits.empty')}
      </p>
    );
  }
  return (
    <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
      {commits.map((commit) => (
        <li key={commit.hash} className="flex items-start gap-3 px-4 py-3">
          <GitCommitHorizontal className="mt-0.5 h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm text-app">{commit.subject}</p>
            <p className="mt-0.5 text-xs text-muted">
              {commit.authorName} ·{' '}
              {new Date(commit.authoredAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}
            </p>
          </div>
          <code className="shrink-0 font-mono text-xs text-muted">{commit.shortHash}</code>
        </li>
      ))}
    </ul>
  );
}

interface MergeRequestDetailProps {
  project: Project;
  number: number;
  signedIn: boolean;
  mayMerge: boolean;
  login: string | null;
  onBack: () => void;
  /** Opens another request of the same stack. */
  onOpen: (number: number) => void;
}

/** One merge request: its review, its commits and its changes. */
export function MergeRequestDetail({
  project,
  number,
  signedIn,
  mayMerge,
  login,
  onBack,
  onOpen,
}: MergeRequestDetailProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [request, setRequest] = useState<MergeRequest | null>(null);
  const [comments, setComments] = useState<ReviewComment[]>([]);
  const [commits, setCommits] = useState<MergeCommit[]>([]);
  const [changes, setChanges] = useState<FileChange[]>([]);
  const [tab, setTab] = useState<Tab>('discussion');
  const [conflicts, setConflicts] = useState<string[]>([]);
  const [body, setBody] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);
  const [approvalState, setApprovalState] = useState<ApprovalState | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchMergeRequest(owner, slug, number, controller.signal),
      fetchReviewComments(owner, slug, number, controller.signal),
      fetchMergeCommits(owner, slug, number, controller.signal),
      fetchChanges(owner, slug, number, controller.signal),
    ])
      .then(([found, review, history, files]) => {
        setRequest(found);
        setComments(review);
        setCommits(history);
        setChanges(files);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('merges.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, number, reloads, t]);

  useEffect(() => {
    const controller = new AbortController();
    fetchApprovals(owner, slug, number, controller.signal)
      .then(setApprovalState)
      .catch(() => {
        // A visitor who may not read them simply sees no panel.
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, number, reloads]);

  useEffect(() => {
    const controller = new AbortController();
    fetchFindings(owner, slug, number, controller.signal)
      .then(setFindings)
      .catch(() => {
        // No run of the branch yet means nothing to show, not a failure.
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, number, reloads]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  // Applying a suggestion answers with the commit, not the request, so it
  // has its own handler instead of bending the one that updates the request.
  const apply = (commentId: string): void => {
    setBusy(true);
    setError(null);
    applySuggestion(owner, slug, number, commentId)
      .then(reload)
      .catch(() => {
        setError(t('merges.suggestion.error'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const act = (run: () => Promise<MergeRequest>, failure: TranslationKey): void => {
    setBusy(true);
    setError(null);
    run()
      .then((updated) => {
        setRequest(updated);
        setConflicts([]);
      })
      .catch((cause: unknown) => {
        const found = conflictsOf(cause);
        setConflicts(found);
        setError(t(found.length > 0 ? 'merges.conflict.heading' : failure));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const comment = async (path: string | null, line: number | null, text: string): Promise<void> => {
    try {
      const added = await addReviewComment(owner, slug, number, {
        body: text,
        filePath: path,
        lineNumber: line,
      });
      setComments((current) => [...current, added]);
    } catch {
      setError(t('merges.error.comment'));
    }
  };

  const submitGeneral = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    void comment(null, null, body).finally(() => {
      setBody('');
      setBusy(false);
    });
  };

  const drop = (commentId: string): void => {
    removeReviewComment(owner, slug, number, commentId)
      .then(reload)
      .catch(() => {
        setError(t('merges.error.change'));
      });
  };

  if (error !== null && request === null) return <ErrorBanner message={error} />;

  if (request === null) {
    return (
      <p className="flex items-center gap-2 text-sm text-muted">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('merges.loading')}
      </p>
    );
  }

  const mayChange = signedIn && (mayMerge || request.author.login === login);
  const formatDate = (value: string): string =>
    new Date(value).toLocaleString(i18n.resolvedLanguage ?? 'pl');

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={onBack}
        className="flex items-center gap-2 text-sm text-muted hover:text-app"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {t('merges.backToList')}
      </button>

      {error !== null && <ErrorBanner message={error} />}

      <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
        <div className="min-w-0 flex-1 space-y-4">
          <div className="rounded-xl border border-app bg-surface p-4 shadow-app-sm">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="min-w-0 flex-1 text-lg font-semibold text-app">{request.title}</h1>
              <StateBadge state={request.state} />
            </div>
            <p className="mt-1 text-xs text-muted">
              {t('merges.openedBy', {
                number: request.number,
                author: request.author.displayName,
                date: formatDate(request.createdAt),
              })}
            </p>
            <div className="mt-2">
              <BranchPair from={request.sourceBranch} to={request.targetBranch} />
            </div>
            {request.description !== '' && (
              <p className="mt-3 whitespace-pre-wrap text-sm text-app">{request.description}</p>
            )}
          </div>

          <div className="flex flex-wrap gap-1 rounded-lg border border-app bg-surface p-1">
            {TABS.map((item) => (
              <button
                key={item}
                type="button"
                onClick={() => {
                  setTab(item);
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

          {tab === 'commits' && <CommitTab commits={commits} />}

          {tab === 'changes' && (
            <DiffView
              files={changes}
              comments={comments}
              findings={findings}
              onComment={signedIn ? (path, line, text) => comment(path, line, text) : null}
              onApply={mayMerge ? apply : null}
              onRemoveComment={signedIn ? drop : null}
            />
          )}

          {tab === 'discussion' && (
            <section aria-labelledby="review-heading" className="space-y-3">
              <h2
                id="review-heading"
                className="text-sm font-semibold uppercase tracking-wider text-muted"
              >
                {t('merges.comment.heading')}
              </h2>

              {comments.length === 0 && (
                <p className="text-sm text-muted">{t('merges.comment.none')}</p>
              )}

              <ul className="space-y-3">
                {comments.map((item) => (
                  <li
                    key={item.id}
                    className="rounded-xl border border-app bg-surface p-4 shadow-app-sm"
                  >
                    <p className="mb-1 text-xs text-muted">
                      <span className="font-medium text-app">{item.author.displayName}</span> ·{' '}
                      {formatDate(item.createdAt)}
                      {item.filePath !== null && item.lineNumber !== null && (
                        <>
                          {' · '}
                          <span className="font-mono">
                            {t('merges.comment.at', {
                              line: item.lineNumber,
                              path: item.filePath,
                            })}
                          </span>
                        </>
                      )}
                    </p>
                    <p className="whitespace-pre-wrap text-sm text-app">{item.body}</p>
                  </li>
                ))}
              </ul>

              {signedIn && (
                <form className="space-y-2" onSubmit={submitGeneral}>
                  <label htmlFor="reviewBody" className="sr-only">
                    {t('merges.comment.label')}
                  </label>
                  <textarea
                    id="reviewBody"
                    rows={3}
                    required
                    value={body}
                    onChange={(event) => {
                      setBody(event.target.value);
                    }}
                    placeholder={t('merges.comment.placeholder')}
                    className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
                  />
                  <button
                    type="submit"
                    disabled={busy}
                    className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                  >
                    {t('merges.comment.submit')}
                  </button>
                </form>
              )}
            </section>
          )}
        </div>

        <MergePanel
          request={request}
          conflicts={conflicts}
          stack={<StackPanel owner={owner} slug={slug} number={number} onOpen={onOpen} />}
          approvals={
            <ApprovalPanel
              owner={owner}
              slug={slug}
              number={number}
              state={approvalState}
              login={login}
              open={request.state === 'open'}
              onChanged={reload}
            />
          }
          approved={approvalState?.satisfied ?? true}
          queue={
            <QueuePanel
              owner={owner}
              slug={slug}
              number={number}
              mayMerge={mayMerge}
              open={request.state === 'open'}
              onChanged={reload}
            />
          }
          mayMerge={mayMerge}
          mayChange={mayChange}
          busy={busy}
          onMerge={() => {
            act(() => mergeMergeRequest(owner, slug, number), 'merges.error.merge');
          }}
          onClose={() => {
            act(() => closeMergeRequest(owner, slug, number), 'merges.error.change');
          }}
          onReopen={() => {
            act(() => reopenMergeRequest(owner, slug, number), 'merges.error.change');
          }}
        />
      </div>
    </div>
  );
}
