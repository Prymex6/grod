import { Building2, Globe, Loader2, Lock, Trash2, UserPlus, Users } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import { ProjectList } from '../projects/ProjectList';
import type { Project, Visibility } from '../projects/api';
import {
  addGroupMember,
  fetchGroup,
  fetchGroupMembers,
  fetchGroupProjects,
  removeGroupMember,
  type Group,
  type GroupMember,
  type GroupRole,
} from './api';

const HTTP_NOT_FOUND = 404;
const HTTP_CONFLICT = 409;
const ROLES = ['guest', 'developer', 'maintainer', 'owner'] as const;

const ROLE_KEYS = {
  guest: 'groups.role.guest',
  developer: 'groups.role.developer',
  maintainer: 'groups.role.maintainer',
  owner: 'groups.role.owner',
} as const satisfies Record<GroupRole, TranslationKey>;

const VISIBILITY_ICON = {
  private: Lock,
  internal: Building2,
  public: Globe,
} as const satisfies Record<Visibility, typeof Lock>;

const VISIBILITY_KEY = {
  private: 'projects.visibility.private',
  internal: 'projects.visibility.internal',
  public: 'projects.visibility.public',
} as const satisfies Record<Visibility, TranslationKey>;

const MANAGING_ROLES: GroupRole[] = ['maintainer', 'owner'];

/** One group: what it holds and who takes part in it. */
export function GroupPage(): ReactNode {
  const { t } = useTranslation();
  const { slug = '' } = useParams();
  const [group, setGroup] = useState<Group | null>(null);
  const [projects, setProjects] = useState<Project[]>([]);
  const [members, setMembers] = useState<GroupMember[]>([]);
  const [login, setLogin] = useState('');
  const [role, setRole] = useState<GroupRole>('developer');
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    Promise.all([
      fetchGroup(slug, controller.signal),
      fetchGroupProjects(slug, controller.signal),
      fetchGroupMembers(slug, controller.signal),
    ])
      .then(([found, held, people]) => {
        setGroup(found);
        setProjects(held);
        setMembers(people);
      })
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, [slug, reloads]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    addGroupMember(slug, { login: login.trim(), role })
      .then(() => {
        setLogin('');
        reload();
      })
      .catch((cause: unknown) => {
        if (cause instanceof ApiError && cause.status === HTTP_NOT_FOUND) {
          setError(t('members.error.unknownAccount'));
        } else if (cause instanceof ApiError && cause.status === HTTP_CONFLICT) {
          setError(t('groups.error.lastOwner'));
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
    removeGroupMember(slug, memberLogin)
      .then(reload)
      .catch((cause: unknown) => {
        const last = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(last ? 'groups.error.lastOwner' : 'members.error.add'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  if (failed) {
    return (
      <div className="p-4 sm:p-6">
        <ErrorBanner message={t('groups.error.notFound')} />
      </div>
    );
  }

  if (group === null) {
    return (
      <p className="flex items-center gap-2 p-4 text-sm text-muted sm:p-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('groups.loading')}
      </p>
    );
  }

  const VisibilityIcon = VISIBILITY_ICON[group.visibility];
  const mayManage = group.role !== null && MANAGING_ROLES.includes(group.role);

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <Users className="h-6 w-6 text-accent" aria-hidden="true" />
          <h1 className="text-2xl font-semibold tracking-tight text-app">{group.name}</h1>
          <span className="font-mono text-sm text-accent">{group.slug}</span>
          <span className="flex items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
            <VisibilityIcon className="h-3 w-3" aria-hidden="true" />
            {t(VISIBILITY_KEY[group.visibility])}
          </span>
        </div>
        {group.description !== '' && <p className="text-sm text-muted">{group.description}</p>}
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <section aria-labelledby="group-projects" className="space-y-3">
        <h2
          id="group-projects"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('groups.projects')}
        </h2>
        {projects.length === 0 ? (
          <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
            {t('groups.noProjects')}
          </p>
        ) : (
          <ProjectList projects={projects} />
        )}
      </section>

      <section aria-labelledby="group-members" className="space-y-3">
        <h2
          id="group-members"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('groups.members')}
        </h2>

        <div className="overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          <ul className="divide-y divide-app">
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
                {mayManage && (
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
                )}
              </li>
            ))}
          </ul>
        </div>

        {mayManage && (
          <form className="flex flex-wrap items-end gap-3" onSubmit={add}>
            <div className="min-w-48 flex-1">
              <label htmlFor="groupMember" className="mb-1.5 block text-sm font-medium text-app">
                {t('members.field.login')}
              </label>
              <input
                id="groupMember"
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
              <label htmlFor="groupRole" className="mb-1.5 block text-sm font-medium text-app">
                {t('members.field.role')}
              </label>
              <select
                id="groupRole"
                value={role}
                onChange={(event) => {
                  setRole(event.target.value as GroupRole);
                }}
                className="rounded-lg border border-app bg-surface px-2 py-2 text-sm text-app focus:border-accent focus:outline-none"
              >
                {ROLES.filter((item) => item !== 'owner' || group.role === 'owner').map((item) => (
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
        )}
      </section>
    </div>
  );
}
