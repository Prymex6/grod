import { Building2, Globe, Loader2, Lock, Plus, Users } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import type { Visibility } from '../projects/api';
import { createGroup, fetchGroups, type Group } from './api';

const HTTP_CONFLICT = 409;
const SLUG_MAX_LENGTH = 64;
const NAME_MAX_LENGTH = 100;

const VISIBILITIES = ['private', 'internal', 'public'] as const;

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

/** Groups the signed-in account belongs to, with a form to start a new one. */
export function GroupsPage(): ReactNode {
  const { t } = useTranslation();
  const [groups, setGroups] = useState<Group[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [slug, setSlug] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('private');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchGroups(controller.signal)
      .then(setGroups)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('groups.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const submit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createGroup({ slug: slug.trim(), name, description, visibility })
      .then(() => {
        setSlug('');
        setName('');
        setDescription('');
        setCreating(false);
        setReloads((count) => count + 1);
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'groups.error.taken' : 'groups.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-app">{t('groups.title')}</h1>
          <p className="mt-1 text-sm text-muted">{t('groups.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('groups.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={submit}
        >
          <div className="flex flex-wrap gap-3">
            <div className="min-w-48 flex-1">
              <label htmlFor="groupSlug" className="mb-1.5 block text-sm font-medium text-app">
                {t('groups.field.slug')}
              </label>
              <input
                id="groupSlug"
                type="text"
                required
                maxLength={SLUG_MAX_LENGTH}
                value={slug}
                onChange={(event) => {
                  setSlug(event.target.value);
                }}
                placeholder="kowalscy"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
              <p className="mt-1 text-xs text-muted">{t('groups.field.slugHint')}</p>
            </div>
            <div className="min-w-48 flex-1">
              <label htmlFor="groupName" className="mb-1.5 block text-sm font-medium text-app">
                {t('groups.field.name')}
              </label>
              <input
                id="groupName"
                type="text"
                required
                maxLength={NAME_MAX_LENGTH}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none"
              />
            </div>
          </div>
          <div>
            <label htmlFor="groupDescription" className="mb-1.5 block text-sm font-medium text-app">
              {t('groups.field.description')}
            </label>
            <input
              id="groupDescription"
              type="text"
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none"
            />
          </div>
          <div>
            <label htmlFor="groupVisibility" className="mb-1.5 block text-sm font-medium text-app">
              {t('groups.field.visibility')}
            </label>
            <select
              id="groupVisibility"
              value={visibility}
              onChange={(event) => {
                setVisibility(event.target.value as Visibility);
              }}
              className="rounded-lg border border-app bg-surface px-2 py-2 text-sm text-app focus:border-accent focus:outline-none"
            >
              {VISIBILITIES.map((item) => (
                <option key={item} value={item}>
                  {t(VISIBILITY_KEY[item])}
                </option>
              ))}
            </select>
          </div>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {busy ? t('groups.creating') : t('groups.create')}
          </button>
        </form>
      )}

      {groups === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('groups.loading')}
        </p>
      )}

      {groups !== null && groups.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('groups.empty')}
        </p>
      )}

      {groups !== null && groups.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {groups.map((group) => {
            const VisibilityIcon = VISIBILITY_ICON[group.visibility];
            return (
              <li key={group.id}>
                <Link
                  to={`/groups/${group.slug}`}
                  className="flex items-center gap-3 px-4 py-3 hover:bg-surface-raised"
                >
                  <Users className="h-5 w-5 shrink-0 text-muted" aria-hidden="true" />
                  <div className="min-w-0 flex-1">
                    <p className="flex flex-wrap items-center gap-2">
                      <span className="truncate text-sm font-medium text-app">{group.name}</span>
                      <span className="truncate font-mono text-xs text-accent">{group.slug}</span>
                      <span className="flex items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                        <VisibilityIcon className="h-3 w-3" aria-hidden="true" />
                        {t(VISIBILITY_KEY[group.visibility])}
                      </span>
                    </p>
                    {group.description !== '' && (
                      <p className="mt-0.5 truncate text-xs text-muted">{group.description}</p>
                    )}
                  </div>
                  <span className="shrink-0 text-xs text-muted">
                    {t('groups.memberCount', { count: group.memberCount })}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
