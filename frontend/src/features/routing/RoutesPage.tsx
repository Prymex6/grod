import { ExternalLink, Globe, Loader2, Lock, Plus, Route as RouteIcon, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { ApiError } from '../../lib/api';
import { createRoute, deleteRoute, fetchRoutes, type Route, type RouteTarget } from './api';

const HTTP_CONFLICT = 409;
const NAME_MAX_LENGTH = 63;

/** Names that stand in front of what the platform runs. */
export function RoutesPage(): ReactNode {
  const { t } = useTranslation();
  const [routes, setRoutes] = useState<Route[] | null>(null);
  const [creating, setCreating] = useState(false);
  const [name, setName] = useState('');
  const [targetKind, setTargetKind] = useState<RouteTarget>('application');
  const [target, setTarget] = useState('');
  const [isPublic, setIsPublic] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchRoutes(controller.signal)
      .then(setRoutes)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('routing.error.load'));
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    createRoute({
      name: name.trim().toLowerCase(),
      targetKind,
      target: target.trim(),
      public: isPublic,
    })
      .then(() => {
        setName('');
        setTarget('');
        setCreating(false);
        setReloads((count) => count + 1);
      })
      .catch((cause: unknown) => {
        const taken = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(taken ? 'routing.error.taken' : 'routing.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const drop = (routeName: string): void => {
    setBusy(true);
    deleteRoute(routeName)
      .then(() => {
        setReloads((count) => count + 1);
      })
      .catch(() => {
        setError(t('routing.error.create'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <RouteIcon className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('routing.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('routing.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('routing.create')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="flex flex-wrap gap-3">
            <div className="min-w-40 flex-1">
              <label htmlFor="routeName" className="mb-1.5 block text-sm font-medium text-app">
                {t('routing.field.name')}
              </label>
              <input
                id="routeName"
                type="text"
                required
                maxLength={NAME_MAX_LENGTH}
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                }}
                placeholder="moja-apka"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
            <div>
              <label htmlFor="routeKind" className="mb-1.5 block text-sm font-medium text-app">
                {t('routing.field.kind')}
              </label>
              <select
                id="routeKind"
                value={targetKind}
                onChange={(event) => {
                  setTargetKind(event.target.value as RouteTarget);
                }}
                className="rounded-lg border border-app bg-surface px-2 py-2 text-sm text-app focus:border-accent focus:outline-none"
              >
                <option value="application">{t('routing.kind.application')}</option>
                <option value="address">{t('routing.kind.address')}</option>
              </select>
            </div>
            <div className="min-w-48 flex-1">
              <label htmlFor="routeTarget" className="mb-1.5 block text-sm font-medium text-app">
                {t('routing.field.target')}
              </label>
              <input
                id="routeTarget"
                type="text"
                required
                value={target}
                onChange={(event) => {
                  setTarget(event.target.value);
                }}
                placeholder={targetKind === 'application' ? 'serwer-www' : 'http://127.0.0.1:8080'}
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
          </div>
          <label className="flex items-center gap-2 text-sm text-app">
            <input
              type="checkbox"
              checked={isPublic}
              onChange={(event) => {
                setIsPublic(event.target.checked);
              }}
              className="h-4 w-4 accent-[var(--accent)]"
            />
            {t('routing.field.public')}
          </label>
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('routing.create')}
          </button>
        </form>
      )}

      {routes === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('routing.loading')}
        </p>
      )}

      {routes !== null && routes.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('routing.empty')}
        </p>
      )}

      {routes !== null && routes.length > 0 && (
        <ul className="divide-y divide-app overflow-hidden rounded-xl border border-app bg-surface shadow-app-sm">
          {routes.map((route) => {
            const AccessIcon = route.public ? Globe : Lock;
            return (
              <li key={route.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                <RouteIcon className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
                <div className="min-w-0 flex-1">
                  <a
                    href={route.url}
                    target="_blank"
                    rel="noreferrer"
                    className="flex min-w-0 items-center gap-1 truncate font-mono text-sm text-accent hover:underline"
                  >
                    {route.url}
                    <ExternalLink className="h-3 w-3 shrink-0" aria-hidden="true" />
                  </a>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">
                    →{' '}
                    {route.targetKind === 'application'
                      ? t('routing.kind.application')
                      : t('routing.kind.address')}
                    : {route.target}
                  </p>
                </div>
                <span className="flex shrink-0 items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                  <AccessIcon className="h-3 w-3" aria-hidden="true" />
                  {t(route.public ? 'routing.public' : 'routing.private')}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    drop(route.name);
                  }}
                  disabled={busy}
                  aria-label={t('routing.remove', { name: route.name })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
