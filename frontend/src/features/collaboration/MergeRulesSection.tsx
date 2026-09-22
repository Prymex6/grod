import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { Project } from '../projects/api';
import { fetchMergeRules, setMergeRules } from './api';

const MAX_APPROVALS = 20;

/** How many people must approve, and which jobs must pass, before a merge. */
export function MergeRulesSection({ project }: { project: Project }): ReactNode {
  const { t } = useTranslation();
  const [approvals, setApprovals] = useState(0);
  const [checks, setChecks] = useState('');
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchMergeRules(owner, slug, controller.signal)
      .then((rules) => {
        setApprovals(rules.requiredApprovals);
        setChecks(rules.requiredChecks.join(', '));
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(t('rules.error'));
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, t]);

  const save = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    setSaved(false);
    setMergeRules(owner, slug, {
      requiredApprovals: approvals,
      requiredChecks: checks
        .split(',')
        .map((name) => name.trim())
        .filter((name) => name !== ''),
    })
      .then((rules) => {
        setChecks(rules.requiredChecks.join(', '));
        setSaved(true);
      })
      .catch(() => {
        setError(t('rules.error'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="rules-heading" className="space-y-4">
      <div>
        <h2
          id="rules-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('rules.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('rules.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <form className="flex flex-wrap items-end gap-3" onSubmit={save}>
        <div className="w-32">
          <label htmlFor="requiredApprovals" className="mb-1.5 block text-sm font-medium text-app">
            {t('rules.approvals')}
          </label>
          <input
            id="requiredApprovals"
            type="number"
            min={0}
            max={MAX_APPROVALS}
            value={approvals}
            onChange={(event) => {
              setApprovals(Number(event.target.value));
            }}
            className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none"
          />
        </div>
        <div className="min-w-56 flex-1">
          <label htmlFor="requiredChecks" className="mb-1.5 block text-sm font-medium text-app">
            {t('rules.checks')}
          </label>
          <input
            id="requiredChecks"
            type="text"
            value={checks}
            onChange={(event) => {
              setChecks(event.target.value);
            }}
            placeholder="testy, lintery"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {t('rules.save')}
        </button>
      </form>

      {saved && <p className="text-sm text-success">{t('rules.saved')}</p>}
    </section>
  );
}
