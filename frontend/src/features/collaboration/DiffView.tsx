import { Bot, ChevronDown, ChevronRight, MessageSquarePlus, Trash2, Wand2 } from 'lucide-react';
import { useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { parsePatch, type DiffHunk, type LineKind } from './diff';
import type { FileChange, Finding, ReviewComment } from './api';

const LINE_CLASSES = {
  added: 'bg-success-subtle border-l-2 border-success',
  removed: 'bg-error-subtle border-l-2 border-error',
  context: 'border-l-2 border-transparent',
} as const satisfies Record<LineKind, string>;

const LINE_SIGN = { added: '+', removed: '−', context: ' ' } as const satisfies Record<
  LineKind,
  string
>;

/** The fence a reviewer writes the replacement in, as GitHub does it. */
const SUGGESTION = /```suggestion[^\n]*\n([\s\S]*?)```/;

interface CommentRowProps {
  comment: ReviewComment;
  onRemove: ((id: string) => void) | null;
  /** Set when whoever is looking may push, so the suggestion can be taken. */
  onApply: ((id: string) => void) | null;
}

/** One review comment, shown inside the diff under the line it belongs to. */
function CommentRow({ comment, onRemove, onApply }: CommentRowProps): ReactNode {
  const { t, i18n } = useTranslation();
  const suggested = SUGGESTION.exec(comment.body)?.[1] ?? null;
  return (
    <div className="border-l-2 border-accent bg-accent-subtle px-3 py-2">
      <div className="rounded-xl border border-app bg-surface p-2 text-xs">
        <p className="mb-1 flex items-center gap-2 text-muted">
          <span className="font-medium text-app">{comment.author.displayName}</span>
          <span>·</span>
          <span>{new Date(comment.createdAt).toLocaleString(i18n.resolvedLanguage ?? 'pl')}</span>
          {onRemove !== null && (
            <button
              type="button"
              onClick={() => {
                onRemove(comment.id);
              }}
              aria-label={t('merges.comment.remove')}
              className="ml-auto rounded-md p-1 text-muted hover:bg-surface-raised hover:text-error"
            >
              <Trash2 className="h-3 w-3" aria-hidden="true" />
            </button>
          )}
        </p>
        <p className="whitespace-pre-wrap text-app">{comment.body}</p>

        {suggested !== null && onApply !== null && (
          <button
            type="button"
            onClick={() => {
              onApply(comment.id);
            }}
            className="mt-2 flex items-center gap-1.5 rounded-lg bg-accent px-2.5 py-1 text-xs font-medium text-accent-contrast hover:bg-accent-hover"
          >
            <Wand2 className="h-3 w-3" aria-hidden="true" />
            {t('merges.suggestion.apply')}
          </button>
        )}
      </div>
    </div>
  );
}

interface FindingRowProps {
  finding: Finding;
}

/** One remark a tool made, shown under the line it is about. */
function FindingRow({ finding }: FindingRowProps): ReactNode {
  const { t } = useTranslation();
  return (
    <div className="border-l-2 border-warning bg-warning-subtle px-3 py-2">
      <p className="flex items-start gap-2 text-xs">
        <Bot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-warning" aria-hidden="true" />
        <span className="text-app">
          <span className="font-mono text-muted">{finding.tool}</span>{' '}
          <span className="sr-only">{t('merges.finding.label')}</span>
          {finding.message}
        </span>
      </p>
    </div>
  );
}

interface HunkProps {
  hunk: DiffHunk;
  path: string;
  commentsOf: (line: number) => ReviewComment[];
  findingsOf: (line: number) => Finding[];
  onApply: ((id: string) => void) | null;
  onComment: ((line: number, body: string) => Promise<void>) | null;
  onRemoveComment: ((id: string) => void) | null;
}

/** One `@@` block of a file, with the review that hangs off its lines. */
function Hunk({
  hunk,
  path,
  commentsOf,
  findingsOf,
  onComment,
  onApply,
  onRemoveComment,
}: HunkProps): ReactNode {
  const { t } = useTranslation();
  const [writingAt, setWritingAt] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);

  const lineKey = (index: number): string => `${path}:${hunk.header}:${index.toString()}`;

  const send = (line: number): void => {
    if (onComment === null) return;
    setBusy(true);
    void onComment(line, draft.trim()).finally(() => {
      setBusy(false);
      setDraft('');
      setWritingAt(null);
    });
  };

  return (
    <div className="min-w-full">
      <div className="bg-surface-raised px-3 py-1 font-mono text-xs text-muted">{hunk.header}</div>
      {hunk.lines.map((line, index) => {
        // Only a line that exists after the change can carry a comment.
        const target = line.newNumber;
        return (
          <div key={lineKey(index)}>
            <div
              className={`group flex min-w-full items-stretch font-mono text-xs ${LINE_CLASSES[line.kind]}`}
            >
              <span className="w-10 shrink-0 select-none px-1 text-right text-muted">
                {line.oldNumber ?? ''}
              </span>
              <span className="w-10 shrink-0 select-none px-1 text-right text-muted">
                {line.newNumber ?? ''}
              </span>
              <span className="w-4 shrink-0 select-none text-center text-muted">
                {LINE_SIGN[line.kind]}
              </span>
              <span className="flex-1 whitespace-pre px-2 text-app">{line.content || ' '}</span>
              {onComment !== null && target !== null && (
                <button
                  type="button"
                  onClick={() => {
                    setWritingAt(writingAt === target ? null : target);
                    setDraft('');
                  }}
                  aria-label={t('merges.changes.commentOnLine', { line: target })}
                  className="mr-1 shrink-0 self-center rounded-md p-1 text-muted opacity-0 hover:bg-surface-raised hover:text-accent focus-visible:opacity-100 group-hover:opacity-100"
                >
                  <MessageSquarePlus className="h-3.5 w-3.5" aria-hidden="true" />
                </button>
              )}
            </div>

            {target !== null &&
              findingsOf(target).map((finding) => (
                <FindingRow key={`${finding.tool}:${finding.message}`} finding={finding} />
              ))}

            {target !== null &&
              commentsOf(target).map((comment) => (
                <CommentRow
                  key={comment.id}
                  comment={comment}
                  onRemove={onRemoveComment}
                  onApply={onApply}
                />
              ))}

            {target !== null && writingAt === target && (
              <div className="border-y border-app bg-surface-raised p-3">
                <label htmlFor="lineComment" className="sr-only">
                  {t('merges.comment.label')}
                </label>
                <textarea
                  id="lineComment"
                  rows={2}
                  value={draft}
                  onChange={(event) => {
                    setDraft(event.target.value);
                  }}
                  placeholder={t('merges.comment.placeholder')}
                  className="w-full resize-y rounded-lg border border-app bg-surface px-2 py-1 text-sm text-app focus:border-accent focus:outline-none"
                />
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    disabled={busy || draft.trim() === ''}
                    onClick={() => {
                      send(target);
                    }}
                    className="rounded-lg bg-accent px-3 py-1 text-xs font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-50"
                  >
                    {t('merges.comment.submit')}
                  </button>
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

interface FileCardProps {
  file: FileChange;
  comments: ReviewComment[];
  findings: Finding[];
  onApply: ((id: string) => void) | null;
  onComment: ((path: string, line: number, body: string) => Promise<void>) | null;
  onRemoveComment: ((id: string) => void) | null;
}

/** One changed file: its path, its counters and its patch. */
function FileCard({
  file,
  comments,
  findings,
  onComment,
  onApply,
  onRemoveComment,
}: FileCardProps): ReactNode {
  const { t } = useTranslation();
  const [collapsed, setCollapsed] = useState(false);
  const Chevron = collapsed ? ChevronRight : ChevronDown;
  const hunks = file.binary ? [] : parsePatch(file.patch);

  const commentsOf = (line: number): ReviewComment[] =>
    comments.filter((comment) => comment.filePath === file.path && comment.lineNumber === line);
  const findingsOf = (line: number): Finding[] =>
    findings.filter((finding) => finding.path === file.path && finding.line === line);

  return (
    <article className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
      <header className="flex flex-wrap items-center gap-2 border-b border-app bg-surface-raised px-3 py-2">
        <button
          type="button"
          onClick={() => {
            setCollapsed((value) => !value);
          }}
          aria-expanded={!collapsed}
          aria-label={t(collapsed ? 'merges.changes.expand' : 'merges.changes.collapse', {
            path: file.path,
          })}
          className="rounded-md p-1 text-muted hover:bg-surface hover:text-app"
        >
          <Chevron className="h-4 w-4" aria-hidden="true" />
        </button>
        <span className="min-w-0 flex-1 truncate font-mono text-xs text-app">{file.path}</span>
        <span className="font-mono text-xs">
          <span className="text-success">+{file.additions}</span>{' '}
          <span className="text-error">−{file.deletions}</span>
        </span>
      </header>

      {!collapsed && (
        <div className="overflow-x-auto">
          {file.binary ? (
            <p className="p-3 text-sm text-muted">{t('merges.changes.binary')}</p>
          ) : (
            hunks.map((hunk, index) => (
              <Hunk
                key={`${file.path}:${hunk.header}:${index.toString()}`}
                hunk={hunk}
                path={file.path}
                commentsOf={commentsOf}
                findingsOf={findingsOf}
                onApply={onApply}
                onComment={
                  onComment === null ? null : (line, body) => onComment(file.path, line, body)
                }
                onRemoveComment={onRemoveComment}
              />
            ))
          )}
        </div>
      )}
    </article>
  );
}

interface DiffViewProps {
  files: FileChange[];
  comments: ReviewComment[];
  /** What the tools said about these lines, from the last run of the branch. */
  findings: Finding[];
  onApply: ((id: string) => void) | null;
  onComment: ((path: string, line: number, body: string) => Promise<void>) | null;
  onRemoveComment: ((id: string) => void) | null;
}

/** Every file a merge request changes, with the review pinned to its lines. */
export function DiffView({
  files,
  comments,
  findings,
  onComment,
  onApply,
  onRemoveComment,
}: DiffViewProps): ReactNode {
  const { t } = useTranslation();

  if (files.length === 0) {
    return (
      <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
        {t('merges.changes.empty')}
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      {files.map((file) => (
        <FileCard
          key={file.path}
          file={file}
          comments={comments}
          findings={findings}
          onComment={onComment}
          onApply={onApply}
          onRemoveComment={onRemoveComment}
        />
      ))}
    </div>
  );
}
