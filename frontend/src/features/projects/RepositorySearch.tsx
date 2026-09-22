import { Search } from 'lucide-react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { searchRepository, type Project, type SearchMatch } from './api';

const MIN_QUERY_LENGTH = 2;

/** Finds a phrase in the files of one branch, the way `git grep` does. */
export function RepositorySearch({
  project,
  reference,
}: {
  project: Project;
  reference: string;
}): ReactNode {
  const { t } = useTranslation();
  const [query, setQuery] = useState('');
  const [matches, setMatches] = useState<SearchMatch[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (query.trim().length < MIN_QUERY_LENGTH) return;

    setSearching(true);
    setError(null);
    searchRepository(project.ownerLogin, project.slug, { query: query.trim(), ref: reference })
      .then(setMatches)
      .catch(() => {
        setError(t('project.search.error'));
      })
      .finally(() => {
        setSearching(false);
      });
  };

  return (
    <div className="space-y-4">
      <form role="search" className="flex flex-wrap items-center gap-3" onSubmit={submit}>
        <div className="flex min-w-64 flex-1 items-center gap-2 rounded-lg border border-app bg-app px-3 py-2 focus-within:border-accent">
          <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
          <input
            type="search"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
            }}
            placeholder={t('project.search.placeholder')}
            aria-label={t('project.search.placeholder')}
            className="w-full bg-transparent text-sm text-app placeholder:text-muted focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={searching || query.trim().length < MIN_QUERY_LENGTH}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {searching ? t('project.search.searching') : t('project.search.submit')}
        </button>
      </form>

      {error !== null && <ErrorBanner message={error} />}

      {matches === null && !searching && (
        <p className="text-sm text-muted">{t('project.search.hint')}</p>
      )}

      {matches !== null && matches.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('project.search.empty')}
        </p>
      )}

      {matches !== null && matches.length > 0 && (
        <>
          <p className="text-xs text-muted">
            {t('project.search.results', { count: matches.length })}
          </p>
          <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
            {matches.map((match) => (
              <li key={`${match.path}:${match.lineNumber.toString()}`} className="px-4 py-3">
                <Link
                  to={`/${project.ownerLogin}/${project.slug}?ref=${encodeURIComponent(reference)}&path=${encodeURIComponent(match.path)}`}
                  className="font-mono text-sm text-accent hover:underline"
                >
                  {match.path}:{match.lineNumber}
                </Link>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all font-mono text-xs text-muted">
                  {match.line.trim()}
                </pre>
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
