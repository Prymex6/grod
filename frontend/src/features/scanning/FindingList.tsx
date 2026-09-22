import { CheckCircle2, EyeOff, Loader2, RotateCw, ShieldAlert, ShieldCheck } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import type { Project } from '../projects/api';
import { fetchFindings, scanNow, setFindingState, type Finding, type FindingState } from './api';

const STATE_CLASS: Record<FindingState, string> = {
  open: 'bg-error-subtle text-error',
  ignored: 'bg-surface-raised text-muted',
  fixed: 'bg-success-subtle text-success',
};

const ruleLabel = (rule: string): TranslationKey => `scanning.rule.${rule}` as TranslationKey;
const stateLabel = (state: FindingState): TranslationKey =>
  `scanning.state.${state}` as TranslationKey;

interface FindingListProps {
  project: Project;
}

/** What the last scan of this repository found, and what to do about it. */
export function FindingList({ project }: FindingListProps): ReactNode {
  const { t, i18n } = useTranslation();
  const [findings, setFindings] = useState<Finding[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const owner = project.ownerLogin;
  const slug = project.slug;

  useEffect(() => {
    const controller = new AbortController();
    fetchFindings(owner, slug, controller.signal)
      .then(setFindings)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('scanning.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [owner, slug, reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const scan = (): void => {
    setBusy(true);
    setError(null);
    scanNow(owner, slug)
      .then(reload)
      .catch(() => {
        setError(t('scanning.error.scan'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const decide = (finding: Finding, state: FindingState): void => {
    setBusy(true);
    setFindingState(owner, slug, finding.id, state)
      .then(reload)
      .catch(() => {
        setError(t('scanning.error.load'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const open = findings?.filter((item) => item.state === 'open').length ?? 0;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <p className="max-w-2xl text-sm text-muted">{t('scanning.description')}</p>
        <button
          type="button"
          onClick={scan}
          disabled={busy}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          <RotateCw className="h-4 w-4" aria-hidden="true" />
          {t('scanning.scan')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {findings === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('scanning.loading')}
        </p>
      )}

      {findings !== null && findings.length === 0 && (
        <div className="space-y-2 rounded-xl border border-app bg-surface px-4 py-6 text-center">
          <ShieldCheck className="mx-auto h-6 w-6 text-success" aria-hidden="true" />
          <p className="text-sm text-muted">{t('scanning.empty')}</p>
        </div>
      )}

      {findings !== null && findings.length > 0 && (
        <>
          <p className="text-sm text-app">
            {open > 0 ? t('scanning.openCount', { count: open }) : t('scanning.nothingOpen')}
          </p>
          <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
            {findings.map((finding) => (
              <li key={finding.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <ShieldAlert
                  className={`h-4 w-4 shrink-0 ${
                    finding.state === 'open' ? 'text-error' : 'text-muted'
                  }`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm text-app">
                    {t(ruleLabel(finding.rule))}
                    <span className="ml-2 font-mono text-xs text-muted">
                      {finding.path}:{finding.line}
                    </span>
                    {!finding.certain && (
                      <span className="ml-2 rounded-full bg-warning-subtle px-2 py-0.5 text-xs text-warning">
                        {t('scanning.uncertain')}
                      </span>
                    )}
                  </p>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">{finding.snippet}</p>
                  <p className="mt-0.5 text-xs text-muted">
                    {t('scanning.lastSeen', {
                      when: new Date(finding.lastSeenAt).toLocaleString(
                        i18n.resolvedLanguage ?? 'pl',
                      ),
                    })}
                  </p>
                </div>
                <span
                  className={`shrink-0 rounded-full px-2 py-0.5 text-xs ${STATE_CLASS[finding.state]}`}
                >
                  {t(stateLabel(finding.state))}
                </span>
                {finding.state === 'open' && (
                  <button
                    type="button"
                    onClick={() => {
                      decide(finding, 'ignored');
                    }}
                    disabled={busy}
                    aria-label={t('scanning.ignore', { path: finding.path })}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-app disabled:opacity-60"
                  >
                    <EyeOff className="h-4 w-4" />
                  </button>
                )}
                {finding.state === 'ignored' && (
                  <button
                    type="button"
                    onClick={() => {
                      decide(finding, 'open');
                    }}
                    disabled={busy}
                    aria-label={t('scanning.reopen', { path: finding.path })}
                    className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-accent disabled:opacity-60"
                  >
                    <CheckCircle2 className="h-4 w-4" />
                  </button>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </div>
  );
}
