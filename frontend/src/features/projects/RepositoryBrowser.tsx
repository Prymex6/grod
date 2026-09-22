import { File, FileCode2, FilePlus2, Folder, Loader2, Pencil, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import { FileEditor } from './FileEditor';
import {
  deleteFile,
  fetchFile,
  fetchTree,
  type Project,
  type RepositoryFile,
  type TreeEntry,
} from './api';
import { highlight } from './highlight';

interface RepositoryBrowserProps {
  project: Project;
  reference: string;
  path: string;
}

interface BrowserProps extends RepositoryBrowserProps {
  /** Set only when the revision shown is a branch this account may write to. */
  editableBranch: { name: string; commit: string } | null;
  onChanged: (path: string) => void;
}

const HTTP_CONFLICT = 409;

const parentOf = (path: string): string => path.split('/').slice(0, -1).join('/');

const linkTo = (project: Project, reference: string, path: string): string => {
  const params = new URLSearchParams({ ref: reference });
  if (path !== '') params.set('path', path);
  return `/${project.ownerLogin}/${project.slug}?${params.toString()}`;
};

function Breadcrumbs({ project, reference, path }: RepositoryBrowserProps): ReactNode {
  const { t } = useTranslation();
  const parts = path === '' ? [] : path.split('/');

  return (
    <nav
      aria-label={t('project.breadcrumbs')}
      className="flex flex-wrap items-center gap-1 text-sm"
    >
      <Link to={linkTo(project, reference, '')} className="font-mono text-accent hover:underline">
        {project.slug}
      </Link>
      {parts.map((part, index) => (
        <span key={`${part}-${index.toString()}`} className="flex items-center gap-1">
          <span className="text-muted">/</span>
          {index === parts.length - 1 ? (
            <span className="font-mono text-app">{part}</span>
          ) : (
            <Link
              to={linkTo(project, reference, parts.slice(0, index + 1).join('/'))}
              className="font-mono text-accent hover:underline"
            >
              {part}
            </Link>
          )}
        </span>
      ))}
    </nav>
  );
}

function FileContents({ file }: { file: RepositoryFile }): ReactNode {
  const { t } = useTranslation();

  if (file.binary || file.text === null) {
    return (
      <p className="px-4 py-6 text-center text-sm text-muted">
        {t('project.binaryFile', { size: file.size.toLocaleString() })}
      </p>
    );
  }

  const plain = file.text.replace(/\n$/u, '');
  const lines = plain.split('\n');
  // Colouring runs over the whole file so the grammar sees the context; the
  // result is split back into lines to keep the numbers beside them.
  const coloured = highlight(file.path, plain)?.split('\n') ?? null;

  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse font-mono text-xs">
        <tbody>
          {lines.map((line, index) => (
            <tr key={index} className="align-top">
              <td className="select-none border-r border-app px-3 py-0.5 text-right text-muted">
                {index + 1}
              </td>
              {coloured === null ? (
                <td className="whitespace-pre px-3 py-0.5 text-app">{line === '' ? ' ' : line}</td>
              ) : (
                <td
                  className="whitespace-pre px-3 py-0.5 text-app"
                  // highlight.js escapes the file contents itself.
                  dangerouslySetInnerHTML={{ __html: coloured[index] ?? ' ' }}
                />
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Tree of one directory, or the contents of one file. */
export function RepositoryBrowser({
  project,
  reference,
  path,
  editableBranch,
  onChanged,
}: BrowserProps): ReactNode {
  const { t } = useTranslation();
  const [entries, setEntries] = useState<TreeEntry[] | null>(null);
  const [file, setFile] = useState<RepositoryFile | null>(null);
  const [failed, setFailed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // The parent remounts this component whenever the revision or path changes,
  // so the effect never has to clear the previous answer itself.
  useEffect(() => {
    const controller = new AbortController();

    // A path is either a directory or a file; try the directory first.
    fetchTree(project.ownerLogin, project.slug, { ref: reference, path }, controller.signal)
      .then(setEntries)
      .catch(() => {
        if (controller.signal.aborted || path === '') {
          if (!controller.signal.aborted) setFailed(true);
          return;
        }
        fetchFile(project.ownerLogin, project.slug, { ref: reference, path }, controller.signal)
          .then(setFile)
          .catch(() => {
            if (!controller.signal.aborted) setFailed(true);
          });
      });

    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, reference, path]);

  const remove = (): void => {
    if (editableBranch === null || file === null) return;
    setError(null);
    deleteFile(project.ownerLogin, project.slug, file.path, {
      message: t('editor.defaultRemove', { path: file.path }),
      branch: editableBranch.name,
      parentCommit: editableBranch.commit,
    })
      .then(() => {
        onChanged(parentOf(file.path));
      })
      .catch((cause: unknown) => {
        const moved = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(moved ? 'editor.error.moved' : 'editor.error.save'));
      });
  };

  return (
    <div className="space-y-3">
      <Breadcrumbs project={project} reference={reference} path={path} />

      {failed && <ErrorBanner message={t('project.error.path')} />}
      {error !== null && <ErrorBanner message={error} />}

      {creating && editableBranch !== null && (
        <FileEditor
          project={project}
          branch={editableBranch.name}
          parentCommit={editableBranch.commit}
          path={path === '' ? '' : `${path}/`}
          initialText=""
          creating
          onSaved={(written) => {
            setCreating(false);
            onChanged(written);
          }}
          onCancel={() => {
            setCreating(false);
          }}
        />
      )}

      {entries === null && file === null && !failed && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('project.loading')}
        </p>
      )}

      {entries !== null && editableBranch !== null && !creating && (
        <button
          type="button"
          onClick={() => {
            setCreating(true);
          }}
          className="flex items-center gap-2 rounded-lg border border-app px-3 py-1.5 text-sm text-muted hover:bg-surface-raised hover:text-app"
        >
          <FilePlus2 className="h-4 w-4" aria-hidden="true" />
          {t('editor.newFile')}
        </button>
      )}

      {entries !== null && !creating && (
        <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          <ul className="divide-y divide-app">
            {path !== '' && (
              <li>
                <Link
                  to={linkTo(project, reference, parentOf(path))}
                  className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-muted hover:bg-surface-raised"
                >
                  <Folder className="h-4 w-4" aria-hidden="true" />
                  ..
                </Link>
              </li>
            )}
            {entries.map((entry) => (
              <li key={entry.path}>
                <Link
                  to={linkTo(project, reference, entry.path)}
                  className="flex items-center gap-2.5 px-4 py-2.5 hover:bg-surface-raised"
                >
                  {entry.type === 'tree' ? (
                    <Folder className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                  ) : (
                    <FileCode2 className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                  )}
                  <span className="min-w-0 flex-1 truncate font-mono text-sm text-app">
                    {entry.name}
                  </span>
                  {entry.size !== null && (
                    <span className="shrink-0 font-mono text-xs text-muted">
                      {entry.size.toLocaleString()} B
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {file !== null && editing && editableBranch !== null && (
        <FileEditor
          project={project}
          branch={editableBranch.name}
          parentCommit={editableBranch.commit}
          path={file.path}
          initialText={file.text ?? ''}
          onSaved={(written) => {
            setEditing(false);
            onChanged(written);
          }}
          onCancel={() => {
            setEditing(false);
          }}
        />
      )}

      {file !== null && !editing && (
        <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          <div className="flex items-center gap-2 border-b border-app px-4 py-2.5">
            <File className="h-4 w-4 text-muted" aria-hidden="true" />
            <span className="font-mono text-sm text-app">{file.path}</span>
            <span className="ml-auto font-mono text-xs text-muted">
              {file.size.toLocaleString()} B
            </span>
            {editableBranch !== null && !file.binary && (
              <button
                type="button"
                onClick={() => {
                  setEditing(true);
                }}
                aria-label={t('editor.edit', { path: file.path })}
                className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent"
              >
                <Pencil className="h-4 w-4" />
              </button>
            )}
            {editableBranch !== null && (
              <button
                type="button"
                onClick={remove}
                aria-label={t('editor.remove', { path: file.path })}
                className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            )}
          </div>
          <FileContents file={file} />
        </div>
      )}
    </div>
  );
}
