import { Loader2, Save, X } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import { writeFile, type Project } from './api';

const HTTP_CONFLICT = 409;
const EDITOR_ROWS = 20;

interface FileEditorProps {
  project: Project;
  branch: string;
  /** Where the branch stood when the file was opened, or null for a new one. */
  parentCommit: string | null;
  path: string;
  initialText: string;
  /** True when the file is not in the repository yet. */
  creating?: boolean;
  onSaved: (path: string) => void;
  onCancel: () => void;
}

/** Editing one file and committing it, without leaving the browser. */
export function FileEditor({
  project,
  branch,
  parentCommit,
  path,
  initialText,
  creating = false,
  onSaved,
  onCancel,
}: FileEditorProps): ReactNode {
  const { t } = useTranslation();
  const [name, setName] = useState(path);
  const [text, setText] = useState(initialText);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const save = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const target = name.trim();
    if (target === '') return;

    setBusy(true);
    setError(null);
    writeFile(project.ownerLogin, project.slug, target, {
      content: text,
      message:
        message.trim() ||
        t(creating ? 'editor.defaultAdd' : 'editor.defaultChange', {
          path: target,
        }),
      branch,
      parentCommit,
    })
      .then(() => {
        onSaved(target);
      })
      .catch((cause: unknown) => {
        const moved = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(moved ? 'editor.error.moved' : 'editor.error.save'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <form className="space-y-3" onSubmit={save}>
      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <div>
          <label htmlFor="filePath" className="mb-1.5 block text-sm font-medium text-app">
            {t('editor.path')}
          </label>
          <input
            id="filePath"
            type="text"
            required
            value={name}
            onChange={(event) => {
              setName(event.target.value);
            }}
            placeholder="docs/notatka.md"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
      )}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        <div className="flex items-center gap-2 border-b border-app px-4 py-2.5">
          <span className="font-mono text-sm text-app">{creating ? name || '…' : path}</span>
          <span className="ml-auto font-mono text-xs text-muted">{branch}</span>
        </div>
        <label htmlFor="fileText" className="sr-only">
          {t('editor.contents')}
        </label>
        <textarea
          id="fileText"
          rows={EDITOR_ROWS}
          value={text}
          onChange={(event) => {
            setText(event.target.value);
          }}
          spellCheck={false}
          className="w-full resize-y bg-app px-4 py-3 font-mono text-xs text-app focus:outline-none"
        />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <div className="min-w-56 flex-1">
          <label htmlFor="commitMessage" className="mb-1.5 block text-sm font-medium text-app">
            {t('editor.message')}
          </label>
          <input
            id="commitMessage"
            type="text"
            value={message}
            onChange={(event) => {
              setMessage(event.target.value);
            }}
            placeholder={t(creating ? 'editor.defaultAdd' : 'editor.defaultChange', {
              path: creating ? name || '…' : path,
            })}
            className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          ) : (
            <Save className="h-4 w-4" aria-hidden="true" />
          )}
          {t('editor.save')}
        </button>
        <button
          type="button"
          onClick={onCancel}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg border border-app px-3 py-2 text-sm text-muted hover:bg-surface-raised hover:text-app disabled:opacity-60"
        >
          <X className="h-4 w-4" aria-hidden="true" />
          {t('editor.cancel')}
        </button>
      </div>
    </form>
  );
}
