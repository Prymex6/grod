import { Box, Download, EyeOff, FolderGit2, Loader2, Plus, Store, Trash2 } from 'lucide-react';
import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useNavigate } from 'react-router';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError } from '../../lib/api';
import {
  deleteOffering,
  fetchMine,
  fetchOfferings,
  publishOffering,
  setPublished,
  takeApplication,
  takeTemplate,
  type Offering,
  type OfferingKind,
} from './api';

const HTTP_CONFLICT = 409;
const SLUG_MAX_LENGTH = 63;

const kindLabel = (kind: OfferingKind): TranslationKey =>
  `templates.kind.${kind}` as TranslationKey;

/** The fair: templates and applications people share on this instance. */
export function MarketPage(): ReactNode {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [offerings, setOfferings] = useState<Offering[] | null>(null);
  const [mine, setMine] = useState<Offering[]>([]);
  const [creating, setCreating] = useState(false);
  const [kind, setKind] = useState<OfferingKind>('template');
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [project, setProject] = useState('');
  const [image, setImage] = useState('');
  // Which offering is being taken, and under what name it will land.
  const [taking, setTaking] = useState<string | null>(null);
  const [wanted, setWanted] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reloads, setReloads] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    fetchOfferings(controller.signal)
      .then(setOfferings)
      .catch(() => {
        if (!controller.signal.aborted) setError(t('templates.error.load'));
      });
    fetchMine(controller.signal)
      .then(setMine)
      .catch(() => {
        // A visitor without an account simply has nothing of their own here.
      });
    return () => {
      controller.abort();
    };
  }, [reloads, t]);

  const reload = (): void => {
    setReloads((count) => count + 1);
  };

  const act = (action: () => Promise<unknown>, failure: TranslationKey): void => {
    setBusy(true);
    setError(null);
    action()
      .then(() => {
        reload();
      })
      .catch((cause: unknown) => {
        const clash = cause instanceof ApiError && cause.status === HTTP_CONFLICT;
        setError(t(clash ? 'templates.error.taken' : failure));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const add = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const [owner = '', name = ''] = project.split('/');
    act(
      () =>
        publishOffering({
          slug: slug.trim().toLowerCase(),
          title: title.trim(),
          description: description.trim(),
          kind,
          owner,
          project: name,
          image: image.trim(),
        }).then(() => {
          setSlug('');
          setTitle('');
          setDescription('');
          setCreating(false);
        }),
      'templates.error.publish',
    );
  };

  const take = (offering: Offering): void => {
    const chosen = wanted.trim().toLowerCase();
    if (chosen === '') return;

    act(() => {
      if (offering.kind === 'template') {
        return takeTemplate(offering.slug, { slug: chosen, name: offering.title }).then((made) => {
          void navigate(`/${made.address}`);
        });
      }
      return takeApplication(offering.slug, chosen).then(() => {
        void navigate('/apps');
      });
    }, 'templates.error.take');
  };

  const isMine = (offering: Offering): boolean => mine.some((item) => item.slug === offering.slug);

  const shown = [...(offerings ?? []), ...mine.filter((item) => !item.published)];

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight text-app">
            <Store className="h-6 w-6 text-accent" aria-hidden="true" />
            {t('templates.title')}
          </h1>
          <p className="mt-1 text-sm text-muted">{t('templates.subtitle')}</p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreating((open) => !open);
          }}
          className="flex items-center gap-2 rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover"
        >
          <Plus className="h-4 w-4" aria-hidden="true" />
          {t('templates.publish')}
        </button>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      {creating && (
        <form
          className="space-y-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
          onSubmit={add}
        >
          <div className="flex flex-wrap gap-3">
            <div>
              <label htmlFor="offeringKind" className="mb-1.5 block text-sm font-medium text-app">
                {t('templates.field.kind')}
              </label>
              <select
                id="offeringKind"
                value={kind}
                onChange={(event) => {
                  setKind(event.target.value as OfferingKind);
                }}
                className="rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none"
              >
                <option value="template">{t('templates.kind.template')}</option>
                <option value="application">{t('templates.kind.application')}</option>
              </select>
            </div>
            <div className="min-w-40 flex-1">
              <label htmlFor="offeringSlug" className="mb-1.5 block text-sm font-medium text-app">
                {t('templates.field.slug')}
              </label>
              <input
                id="offeringSlug"
                type="text"
                required
                maxLength={SLUG_MAX_LENGTH}
                value={slug}
                onChange={(event) => {
                  setSlug(event.target.value);
                }}
                placeholder="szablon-api"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
            <div className="min-w-48 flex-1">
              <label htmlFor="offeringTitle" className="mb-1.5 block text-sm font-medium text-app">
                {t('templates.field.title')}
              </label>
              <input
                id="offeringTitle"
                type="text"
                required
                value={title}
                onChange={(event) => {
                  setTitle(event.target.value);
                }}
                className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none"
              />
            </div>
          </div>

          {kind === 'template' ? (
            <div>
              <label
                htmlFor="offeringProject"
                className="mb-1.5 block text-sm font-medium text-app"
              >
                {t('templates.field.project')}
              </label>
              <input
                id="offeringProject"
                type="text"
                required
                value={project}
                onChange={(event) => {
                  setProject(event.target.value);
                }}
                placeholder="bartek/moj-projekt"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
          ) : (
            <div>
              <label htmlFor="offeringImage" className="mb-1.5 block text-sm font-medium text-app">
                {t('templates.field.image')}
              </label>
              <input
                id="offeringImage"
                type="text"
                required
                value={image}
                onChange={(event) => {
                  setImage(event.target.value);
                }}
                placeholder="nginx:1.27-alpine"
                className="w-full rounded-lg border border-app bg-app px-3 py-2 font-mono text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none"
              />
            </div>
          )}

          <div>
            <label
              htmlFor="offeringDescription"
              className="mb-1.5 block text-sm font-medium text-app"
            >
              {t('templates.field.description')}
            </label>
            <textarea
              id="offeringDescription"
              rows={3}
              value={description}
              onChange={(event) => {
                setDescription(event.target.value);
              }}
              className="w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app focus:border-accent focus:outline-none"
            />
          </div>

          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
          >
            {t('templates.confirm')}
          </button>
        </form>
      )}

      {offerings === null && error === null && (
        <p className="flex items-center gap-2 text-sm text-muted">
          <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
          {t('templates.loading')}
        </p>
      )}

      {offerings !== null && shown.length === 0 && (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('templates.empty')}
        </p>
      )}

      {shown.length > 0 && (
        <ul className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((offering) => (
            <li
              key={offering.slug}
              className="flex flex-col gap-3 rounded-xl border border-app bg-surface p-4 shadow-app-sm"
            >
              <div className="flex items-start gap-2">
                {offering.kind === 'template' ? (
                  <FolderGit2 className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                ) : (
                  <Box className="mt-0.5 h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
                )}
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-app">{offering.title}</p>
                  <p className="mt-0.5 truncate font-mono text-xs text-muted">
                    {offering.author} · {t(kindLabel(offering.kind))}
                  </p>
                </div>
                {!offering.published && (
                  <span className="rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
                    {t('templates.hidden')}
                  </span>
                )}
              </div>

              {offering.description !== '' && (
                <p className="line-clamp-3 text-sm text-muted">{offering.description}</p>
              )}
              {offering.image !== '' && (
                <code className="truncate font-mono text-xs text-muted">{offering.image}</code>
              )}

              <div className="mt-auto flex items-center gap-2">
                <span className="text-xs text-muted">
                  {t('templates.takenCount', { count: offering.taken })}
                </span>
                <button
                  type="button"
                  onClick={() => {
                    setTaking(offering.slug);
                    setWanted(offering.slug);
                  }}
                  disabled={busy || !offering.published}
                  className="ml-auto flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                >
                  <Download className="h-4 w-4" aria-hidden="true" />
                  {t('templates.take')}
                </button>
                {isMine(offering) && (
                  <>
                    <button
                      type="button"
                      onClick={() => {
                        act(
                          () => setPublished(offering.slug, !offering.published),
                          'templates.error.publish',
                        );
                      }}
                      disabled={busy}
                      aria-label={t('templates.hide', { title: offering.title })}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-app disabled:opacity-60"
                    >
                      <EyeOff className="h-4 w-4" />
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        act(() => deleteOffering(offering.slug), 'templates.error.publish');
                      }}
                      disabled={busy}
                      aria-label={t('templates.remove', { title: offering.title })}
                      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-error disabled:opacity-60"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </>
                )}
              </div>

              {taking === offering.slug && (
                <div className="flex flex-wrap items-end gap-2 border-t border-app pt-3">
                  <div className="min-w-32 flex-1">
                    <label
                      htmlFor={`take-${offering.slug}`}
                      className="mb-1.5 block text-xs text-muted"
                    >
                      {t(
                        offering.kind === 'template'
                          ? 'templates.askProject'
                          : 'templates.askApplication',
                      )}
                    </label>
                    <input
                      id={`take-${offering.slug}`}
                      type="text"
                      value={wanted}
                      onChange={(event) => {
                        setWanted(event.target.value);
                      }}
                      className="w-full rounded-lg border border-app bg-app px-3 py-1.5 font-mono text-sm text-app focus:border-accent focus:outline-none"
                    />
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      take(offering);
                    }}
                    disabled={busy}
                    className="rounded-lg bg-accent px-3 py-1.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
                  >
                    {t('templates.confirmTake')}
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
