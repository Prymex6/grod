import { Copy, KeyRound, Loader2, Plus, Trash2, UserPlus } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import {
  RESOURCE_PATHS,
  createServiceAccount,
  deleteServiceAccount,
  fetchGrants,
  fetchResources,
  fetchServiceAccounts,
  revokeGrant,
  writeGrant,
  type Grant,
  type NewServiceAccount,
  type Resource,
  type ResourceKind,
  type Role,
  type ServiceAccount,
  type SubjectKind,
} from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 100;

const KINDS = Object.keys(RESOURCE_PATHS) as ResourceKind[];
const ROLES: Role[] = ['viewer', 'operator', 'admin'];
const SUBJECT_KINDS: SubjectKind[] = ['user', 'group', 'service'];

const kindLabel = (kind: ResourceKind): TranslationKey => `iam.kind.${kind}` as TranslationKey;
const roleLabel = (role: Role): TranslationKey => `iam.role.${role}` as TranslationKey;
const subjectLabel = (kind: SubjectKind): TranslationKey => `iam.subject.${kind}` as TranslationKey;

const SELECT_CLASS =
  'rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none';
const INPUT_CLASS = `${SELECT_CLASS} font-mono placeholder:text-muted`;

/** Machine identities and the permissions they and other people hold. */
export function AccessPage(): ReactNode {
  const { t } = useTranslation();
  const [kind, setKind] = useState<ResourceKind>('bucket');
  // What kind the listing belongs to travels with it, so a listing left over
  // from the previous kind is never shown next to the new one.
  const [loaded, setLoaded] = useState<{ kind: ResourceKind; items: Resource[] } | null>(null);
  const [chosen, setChosen] = useState<string>('');
  const [grants, setGrants] = useState<Grant[]>([]);
  const [accounts, setAccounts] = useState<ServiceAccount[] | null>(null);
  const [fresh, setFresh] = useState<NewServiceAccount | null>(null);
  const [accountName, setAccountName] = useState('');
  const [subjectKind, setSubjectKind] = useState<SubjectKind>('user');
  const [subject, setSubject] = useState('');
  const [role, setRole] = useState<Role>('viewer');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  useEffect(() => {
    const controller = new AbortController();
    fetchServiceAccounts(controller.signal)
      .then(setAccounts)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('iam.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  // Changing the kind loads what there is of it, and picks the first one.
  useEffect(() => {
    const controller = new AbortController();
    fetchResources(kind, controller.signal)
      .then((found) => {
        setLoaded({ kind, items: found });
        setChosen(found[0]?.id ?? '');
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setLoaded({ kind, items: [] });
          setChosen('');
        }
      });
    return () => {
      controller.abort();
    };
  }, [kind, reloads]);

  const resources = loaded !== null && loaded.kind === kind ? loaded.items : null;
  const current = resources?.find((item) => item.id === chosen) ?? null;

  useEffect(() => {
    if (current === null) return undefined;
    const controller = new AbortController();
    fetchGrants(kind, current.id, controller.signal)
      .then(setGrants)
      .catch(() => {
        // Nothing comes back for a resource that is not ours to share.
      });
    return () => {
      controller.abort();
    };
  }, [kind, current, reloads]);

  const give = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    writeGrant({
      resourceKind: kind,
      resourceId: chosen,
      subjectKind,
      subject: subject.trim(),
      role,
    })
      .then(() => {
        setSubject('');
        reload();
      })
      .catch((cause: unknown) => {
        const missing = cause instanceof ApiError && cause.status === 404;
        setError(t(missing ? 'iam.error.noSubject' : 'iam.error.grant'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const take = (grant: Grant): void => {
    setBusy(true);
    setError(null);
    revokeGrant(grant)
      .then(reload)
      .catch(() => {
        setError(t('iam.error.revoke'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const addAccount = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createServiceAccount(accountName.trim())
      .then((created) => {
        setFresh(created);
        setAccountName('');
        reload();
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'iam.error.taken' : 'iam.error.account'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const removeAccount = (name: string): void => {
    setBusy(true);
    setError(null);
    deleteServiceAccount(name)
      .then(() => {
        setFresh((shown) => (shown?.name === name ? null : shown));
        reload();
      })
      .catch(() => {
        setError(t('iam.error.account'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  // A listing that belongs to another resource must not be shown here.
  const shown = current === null ? [] : grants;

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
          <KeyRound className="h-6 w-6 text-accent" aria-hidden="true" />
          {t('iam.title')}
        </h1>
        <p className="mt-1 text-sm text-muted">{t('iam.subtitle')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <section className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
        <h2 className="text-lg font-semibold text-app">{t('iam.grants.title')}</h2>
        <p className="text-sm text-muted">{t('iam.grants.hint')}</p>

        <div className="flex flex-wrap gap-3">
          <div>
            <label htmlFor="grantKind" className="mb-1.5 block text-sm font-medium text-app">
              {t('iam.grants.kind')}
            </label>
            <select
              id="grantKind"
              value={kind}
              onChange={(event) => {
                setKind(event.target.value as ResourceKind);
              }}
              className={SELECT_CLASS}
            >
              {KINDS.map((item) => (
                <option key={item} value={item}>
                  {t(kindLabel(item))}
                </option>
              ))}
            </select>
          </div>
          <div className="min-w-56 flex-1">
            <label htmlFor="grantResource" className="mb-1.5 block text-sm font-medium text-app">
              {t('iam.grants.resource')}
            </label>
            <select
              id="grantResource"
              value={chosen}
              disabled={resources === null || resources.length === 0}
              onChange={(event) => {
                setChosen(event.target.value);
              }}
              className={`${SELECT_CLASS} w-full disabled:opacity-60`}
            >
              {resources?.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {resources !== null && resources.length === 0 && (
          <p className="text-sm text-muted">{t('iam.grants.nothing')}</p>
        )}

        {current !== null && (
          <>
            {shown.length === 0 ? (
              <p className="rounded-lg bg-surface-raised px-4 py-3 text-sm text-muted">
                {t('iam.grants.empty')}
              </p>
            ) : (
              <ul className="divide-y divide-app overflow-hidden rounded-lg border border-app">
                {shown.map((grant) => (
                  <li key={grant.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                    <span className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                      {t(subjectLabel(grant.subjectKind))}
                    </span>
                    <span className="min-w-0 flex-1 truncate font-mono text-sm text-app">
                      {grant.subject}
                    </span>
                    <span className="rounded-md bg-accent-subtle px-2 py-0.5 text-xs text-accent">
                      {t(roleLabel(grant.role))}
                    </span>
                    <button
                      type="button"
                      onClick={() => {
                        take(grant);
                      }}
                      disabled={busy}
                      aria-label={t('iam.grants.revoke', { subject: grant.subject })}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </li>
                ))}
              </ul>
            )}

            <form className="flex flex-wrap items-end gap-3" onSubmit={give}>
              <div>
                <label htmlFor="subjectKind" className="mb-1.5 block text-sm font-medium text-app">
                  {t('iam.grants.subjectKind')}
                </label>
                <select
                  id="subjectKind"
                  value={subjectKind}
                  onChange={(event) => {
                    setSubjectKind(event.target.value as SubjectKind);
                  }}
                  className={SELECT_CLASS}
                >
                  {SUBJECT_KINDS.map((item) => (
                    <option key={item} value={item}>
                      {t(subjectLabel(item))}
                    </option>
                  ))}
                </select>
              </div>
              <div className="min-w-40 flex-1">
                <label htmlFor="subject" className="mb-1.5 block text-sm font-medium text-app">
                  {t('iam.grants.subject')}
                </label>
                <input
                  id="subject"
                  type="text"
                  required
                  maxLength={NAME_MAX_LENGTH}
                  value={subject}
                  onChange={(event) => {
                    setSubject(event.target.value);
                  }}
                  placeholder={t('iam.grants.subjectHint')}
                  className={`${INPUT_CLASS} w-full`}
                />
              </div>
              <div>
                <label htmlFor="grantRole" className="mb-1.5 block text-sm font-medium text-app">
                  {t('iam.grants.role')}
                </label>
                <select
                  id="grantRole"
                  value={role}
                  onChange={(event) => {
                    setRole(event.target.value as Role);
                  }}
                  className={SELECT_CLASS}
                >
                  {ROLES.map((item) => (
                    <option key={item} value={item}>
                      {t(roleLabel(item))}
                    </option>
                  ))}
                </select>
              </div>
              <button
                type="submit"
                disabled={busy}
                className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
              >
                <UserPlus className="h-4 w-4" aria-hidden="true" />
                {t('iam.grants.give')}
              </button>
            </form>
          </>
        )}
      </section>

      <section className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm">
        <h2 className="text-lg font-semibold text-app">{t('iam.services.title')}</h2>
        <p className="text-sm text-muted">{t('iam.services.hint')}</p>

        {fresh !== null && (
          <div className="space-y-2 rounded-lg border border-accent bg-accent-subtle p-3">
            <p className="text-sm text-app">{t('iam.services.once')}</p>
            <div className="flex flex-wrap items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded-md bg-app px-3 py-2 font-mono text-xs text-app">
                {fresh.token}
              </code>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard.writeText(fresh.token);
                }}
                className="flex items-center gap-1.5 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
              >
                <Copy className="h-4 w-4" aria-hidden="true" />
                {t('iam.services.copy')}
              </button>
            </div>
          </div>
        )}

        {accounts === null && error === null && (
          <p className="flex items-center gap-2 text-sm text-muted">
            <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
            {t('iam.loading')}
          </p>
        )}

        {accounts !== null && accounts.length === 0 && (
          <p className="rounded-lg bg-surface-raised px-4 py-3 text-sm text-muted">
            {t('iam.services.empty')}
          </p>
        )}

        {accounts !== null && accounts.length > 0 && (
          <ul className="divide-y divide-app overflow-hidden rounded-lg border border-app">
            {accounts.map((account) => (
              <li key={account.id} className="flex flex-wrap items-center gap-3 px-4 py-2.5">
                <span className="min-w-0 flex-1 truncate font-mono text-sm text-app">
                  {account.name}
                </span>
                <span className="text-xs text-muted">
                  {account.lastUsedAt === null
                    ? t('iam.services.neverUsed')
                    : t('iam.services.lastUsed', {
                        when: new Date(account.lastUsedAt).toLocaleString(),
                      })}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    removeAccount(account.name);
                  }}
                  disabled={busy}
                  aria-label={t('iam.services.remove', { name: account.name })}
                  className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}

        <form className="flex flex-wrap items-end gap-3" onSubmit={addAccount}>
          <div className="min-w-40 flex-1">
            <label htmlFor="accountName" className="mb-1.5 block text-sm font-medium text-app">
              {t('iam.services.name')}
            </label>
            <input
              id="accountName"
              type="text"
              required
              maxLength={NAME_MAX_LENGTH}
              value={accountName}
              onChange={(event) => {
                setAccountName(event.target.value);
              }}
              placeholder="worker-zamowienia"
              className={`${INPUT_CLASS} w-full`}
            />
          </div>
          <button
            type="submit"
            disabled={busy}
            className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            <Plus className="h-4 w-4" aria-hidden="true" />
            {t('iam.services.create')}
          </button>
        </form>
      </section>
    </div>
  );
}
