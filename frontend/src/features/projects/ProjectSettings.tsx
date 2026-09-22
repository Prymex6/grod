import { ShieldCheck, Trash2, TriangleAlert } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { MergeRulesSection } from '../collaboration/MergeRulesSection';
import { ApiError } from '../../lib/api';
import {
  deleteProject,
  fetchProtectedBranches,
  protectBranch,
  unprotectBranch,
  type ProtectedBranch,
  type Project,
} from './api';

const HTTP_CONFLICT = 409;

const SECONDARY_BUTTON =
  'rounded-lg border border-app bg-app px-3 py-2 text-sm font-medium text-app hover:bg-surface-raised disabled:opacity-60';

/** Owner-only settings of a project: protected branches and deletion. */
export function ProjectSettings({ project }: { project: Project }): ReactNode {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [rules, setRules] = useState<ProtectedBranch[]>([]);
  const [pattern, setPattern] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchProtectedBranches(project.ownerLogin, project.slug, controller.signal)
      .then(setRules)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('project.settings.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, t]);

  const reload = async (): Promise<void> => {
    setRules(await fetchProtectedBranches(project.ownerLogin, project.slug));
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    protectBranch(project.ownerLogin, project.slug, pattern)
      .then(async () => {
        setPattern('');
        await reload();
      })
      .catch((cause: unknown) => {
        setError(
          cause instanceof ApiError && cause.status === HTTP_CONFLICT
            ? t('project.settings.alreadyProtected')
            : t('project.settings.error.generic'),
        );
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (rulePattern: string): void => {
    setBusy(true);
    setError(null);
    unprotectBranch(project.ownerLogin, project.slug, rulePattern)
      .then(reload)
      .catch(() => {
        setError(t('project.settings.error.generic'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const remove = (): void => {
    setBusy(true);
    setError(null);
    deleteProject(project.ownerLogin, project.slug)
      .then(() => navigate('/projects'))
      .catch(() => {
        setError(t('project.settings.error.delete'));
        setBusy(false);
      });
  };

  return (
    <div className="max-w-2xl space-y-10">
      {error !== null && <ErrorBanner message={error} />}

      <MergeRulesSection project={project} />

      <section aria-labelledby="protected-heading" className="space-y-4">
        <div>
          <h2
            id="protected-heading"
            className="text-sm font-semibold uppercase tracking-wider text-muted"
          >
            {t('project.settings.protected.heading')}
          </h2>
          <p className="mt-1 text-sm text-muted">{t('project.settings.protected.description')}</p>
        </div>

        <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {rules.length === 0 ? (
            <p className="px-4 py-3 text-sm text-muted">{t('project.settings.protected.empty')}</p>
          ) : (
            <ul className="divide-y divide-app">
              {rules.map((rule) => (
                <li key={rule.id} className="flex items-center justify-between gap-4 px-4 py-3">
                  <p className="flex items-center gap-2 font-mono text-sm text-app">
                    <ShieldCheck className="h-4 w-4 text-success" aria-hidden="true" />
                    {rule.pattern}
                  </p>
                  <button
                    type="button"
                    onClick={() => {
                      drop(rule.pattern);
                    }}
                    disabled={busy}
                    aria-label={t('project.settings.protected.remove', { pattern: rule.pattern })}
                    className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <form className="flex flex-wrap items-end gap-3" onSubmit={add}>
          <div className="min-w-48 flex-1">
            <label htmlFor="pattern" className="mb-1.5 block text-sm font-medium text-app">
              {t('project.settings.protected.pattern')}
            </label>
            <input
              id="pattern"
              type="text"
              required
              maxLength={100}
              value={pattern}
              onChange={(event) => {
                setPattern(event.target.value);
              }}
              placeholder="main"
              className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
            />
            <p className="mt-1.5 text-xs text-muted">
              {t('project.settings.protected.patternHint')}
            </p>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('project.settings.protected.add')}
          </button>
        </form>
      </section>

      <section aria-labelledby="danger-heading" className="space-y-4">
        <div>
          <h2
            id="danger-heading"
            className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wider text-error"
          >
            <TriangleAlert className="h-4 w-4" aria-hidden="true" />
            {t('project.settings.danger.heading')}
          </h2>
          <p className="mt-1 text-sm text-muted">{t('project.settings.danger.description')}</p>
        </div>

        <div className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
          <label htmlFor="confirmation" className="block text-sm text-app">
            {t('project.settings.danger.confirmLabel', { slug: project.slug })}
          </label>
          <input
            id="confirmation"
            type="text"
            value={confirmation}
            onChange={(event) => {
              setConfirmation(event.target.value);
            }}
            placeholder={project.slug}
            className="w-full max-w-sm rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
          <button
            type="button"
            onClick={remove}
            disabled={busy || confirmation !== project.slug}
            className={SECONDARY_BUTTON}
          >
            {t('project.settings.danger.delete')}
          </button>
        </div>
      </section>
    </div>
  );
}
