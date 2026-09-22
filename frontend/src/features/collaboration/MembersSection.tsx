import { Trash2, UserPlus, Users } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import type { Project } from '../projects/api';
import { addMember, fetchMembers, removeMember, type Member, type Role } from './api';

const HTTP_NOT_FOUND = 404;
const HTTP_CONFLICT = 409;
const ROLES = ['guest', 'developer', 'maintainer'] as const;

const ROLE_KEYS = {
  guest: 'members.role.guest',
  developer: 'members.role.developer',
  maintainer: 'members.role.maintainer',
} as const satisfies Record<Role, TranslationKey>;

/** People besides the owner who take part in a project. */
export function MembersSection({ project }: { project: Project }): ReactNode {
  const { t } = useTranslation();
  const [members, setMembers] = useState<Member[]>([]);
  const [login, setLogin] = useState('');
  const [role, setRole] = useState<Role>('developer');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchMembers(project.ownerLogin, project.slug, controller.signal)
      .then(setMembers)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('members.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [project.ownerLogin, project.slug, reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    addMember(project.ownerLogin, project.slug, { login: login.trim(), role })
      .then(() => {
        setLogin('');
        reload();
      })
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.status === HTTP_NOT_FOUND) {
          setError(t('members.error.unknownAccount'));
        } else if (cause instanceof ApiError && cause.status === HTTP_CONFLICT) {
          setError(t('members.error.owner'));
        } else {
          setError(t('members.error.add'));
        }
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (memberLogin: string): void => {
    setBusy(true);
    setError(null);
    removeMember(project.ownerLogin, project.slug, memberLogin)
      .then(reload)
      .catch(() => {
        setError(t('members.error.add'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <section aria-labelledby="members-heading" className="space-y-4">
      <div>
        <h2
          id="members-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('members.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('members.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
        <ul className="divide-y divide-app">
          <li className="flex items-center gap-3 px-4 py-3">
            <Users className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
            <span className="min-w-0 flex-1 truncate text-sm text-app">{project.ownerLogin}</span>
            <span className="shrink-0 rounded-full bg-accent-subtle px-2 py-0.5 text-xs font-medium text-accent">
              {t('members.role.owner')}
            </span>
          </li>
          {members.map((member) => (
            <li key={member.login} className="flex items-center gap-3 px-4 py-3">
              <Users className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm text-app">{member.displayName}</p>
                <p className="truncate font-mono text-xs text-muted">{member.login}</p>
              </div>
              <span className="shrink-0 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                {t(ROLE_KEYS[member.role])}
              </span>
              <button
                type="button"
                onClick={() => {
                  drop(member.login);
                }}
                disabled={busy}
                aria-label={t('members.remove', { login: member.login })}
                className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      </div>

      <form className="flex flex-wrap items-end gap-3" onSubmit={add}>
        <div className="min-w-48 flex-1">
          <label htmlFor="memberLogin" className="mb-1.5 block text-sm font-medium text-app">
            {t('members.field.login')}
          </label>
          <input
            id="memberLogin"
            type="text"
            required
            maxLength={64}
            value={login}
            onChange={(event) => {
              setLogin(event.target.value);
            }}
            placeholder="anna.k"
            className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
          />
        </div>
        <div>
          <label htmlFor="memberRole" className="mb-1.5 block text-sm font-medium text-app">
            {t('members.field.role')}
          </label>
          <select
            id="memberRole"
            value={role}
            onChange={(event) => {
              setRole(event.target.value as Role);
            }}
            className="rounded-lg border border-app bg-surface px-2 py-2 text-sm text-app focus:border-accent focus:outline-none"
          >
            {ROLES.map((item) => (
              <option key={item} value={item}>
                {t(ROLE_KEYS[item])}
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
          {t('members.add')}
        </button>
      </form>
    </section>
  );
}
