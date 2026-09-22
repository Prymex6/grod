import { useEffect, useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ApiError, NetworkError } from '../../lib/api';
import { fetchGroups, type Group } from '../community/api';
import { createProject, type Visibility } from './api';

const SLUG_RULE = /^[a-z0-9][a-z0-9._-]*$/u;
const HTTP_CONFLICT = 409;
const HTTP_UNPROCESSABLE = 422;

const FIELD =
  'w-full rounded-lg border border-app bg-app px-3 py-2 text-sm text-app placeholder:text-muted focus:border-accent focus:outline-none';

const VISIBILITIES: readonly {
  value: Visibility;
  labelKey: TranslationKey;
  hintKey: TranslationKey;
}[] = [
  {
    value: 'private',
    labelKey: 'projects.visibility.private',
    hintKey: 'projects.visibility.privateHint',
  },
  {
    value: 'internal',
    labelKey: 'projects.visibility.internal',
    hintKey: 'projects.visibility.internalHint',
  },
  {
    value: 'public',
    labelKey: 'projects.visibility.public',
    hintKey: 'projects.visibility.publicHint',
  },
];

type ErrorKind = 'taken' | 'invalid' | 'network' | 'unknown';

const ERROR_KEYS = {
  taken: 'projects.error.taken',
  invalid: 'projects.error.invalidSlug',
  network: 'projects.error.network',
  unknown: 'projects.error.unknown',
} as const satisfies Record<ErrorKind, string>;

const classify = (error: unknown): ErrorKind => {
  if (error instanceof NetworkError) return 'network';
  if (error instanceof ApiError) {
    if (error.status === HTTP_CONFLICT) return 'taken';
    if (error.status === HTTP_UNPROCESSABLE) return 'invalid';
  }
  return 'unknown';
};

/** Form that creates a project together with its empty repository. */
export function NewProjectPage(): ReactNode {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [description, setDescription] = useState('');
  const [visibility, setVisibility] = useState<Visibility>('private');
  const [groups, setGroups] = useState<Group[]>([]);
  // Empty means the project belongs to the account itself.
  const [group, setGroup] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<ErrorKind | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchGroups(controller.signal)
      .then((found) => {
        // Only a group the account may fill is worth offering.
        setGroups(found.filter((item) => item.role === 'owner' || item.role === 'maintainer'));
      })
      .catch(() => {
        // Without groups the form still creates personal projects.
      });
    return () => {
      controller.abort();
    };
  }, []);

  const onSubmit = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    if (!SLUG_RULE.test(slug)) {
      setError('invalid');
      return;
    }

    setSubmitting(true);
    setError(null);
    createProject({ slug, name, description, visibility, group: group === '' ? null : group })
      .then((project) => navigate(`/${project.ownerLogin}/${project.slug}`))
      .catch((cause: unknown) => {
        setError(classify(cause));
        setSubmitting(false);
      });
  };

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight text-app">{t('projects.newTitle')}</h1>
        <p className="mt-1 text-sm text-muted">{t('projects.newSubtitle')}</p>
      </div>

      {error !== null && <ErrorBanner message={t(ERROR_KEYS[error])} />}

      <form className="max-w-xl space-y-5" onSubmit={onSubmit}>
        <div>
          <label htmlFor="name" className="mb-1.5 block text-sm font-medium text-app">
            {t('projects.field.name')}
          </label>
          <input
            id="name"
            type="text"
            required
            maxLength={100}
            value={name}
            onChange={(event) => {
              const value = event.target.value;
              setName(value);
              // The address follows the name until it is edited by hand.
              if (slug === '' || slug === name.toLowerCase().replace(/[^a-z0-9._-]+/gu, '-')) {
                setSlug(
                  value
                    .toLowerCase()
                    .replace(/[^a-z0-9._-]+/gu, '-')
                    .replace(/^-+|-+$/gu, ''),
                );
              }
            }}
            placeholder={t('projects.field.namePlaceholder')}
            className={FIELD}
          />
        </div>

        <div>
          <label htmlFor="slug" className="mb-1.5 block text-sm font-medium text-app">
            {t('projects.field.slug')}
          </label>
          <input
            id="slug"
            type="text"
            required
            maxLength={64}
            value={slug}
            onChange={(event) => {
              setSlug(event.target.value);
            }}
            placeholder="moj-projekt"
            className={`${FIELD} font-mono`}
          />
          <p className="mt-1.5 text-xs text-muted">{t('projects.field.slugHint')}</p>
        </div>

        {groups.length > 0 && (
          <div>
            <label htmlFor="group" className="mb-1.5 block text-sm font-medium text-app">
              {t('newProject.group')}
            </label>
            <select
              id="group"
              value={group}
              onChange={(event) => {
                setGroup(event.target.value);
              }}
              className={FIELD}
            >
              <option value="">{t('newProject.groupPersonal')}</option>
              {groups.map((item) => (
                <option key={item.id} value={item.slug}>
                  {item.name} ({item.slug})
                </option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label htmlFor="description" className="mb-1.5 block text-sm font-medium text-app">
            {t('projects.field.description')}
          </label>
          <input
            id="description"
            type="text"
            maxLength={500}
            value={description}
            onChange={(event) => {
              setDescription(event.target.value);
            }}
            placeholder={t('projects.field.descriptionPlaceholder')}
            className={FIELD}
          />
        </div>

        <fieldset>
          <legend className="mb-2 text-sm font-medium text-app">
            {t('projects.field.visibility')}
          </legend>
          <div className="space-y-2">
            {VISIBILITIES.map((option) => (
              <label
                key={option.value}
                className="flex cursor-pointer items-start gap-3 rounded-lg border border-app bg-surface p-3 hover:bg-surface-raised"
              >
                <input
                  type="radio"
                  name="visibility"
                  value={option.value}
                  checked={visibility === option.value}
                  onChange={() => {
                    setVisibility(option.value);
                  }}
                  className="mt-0.5 accent-[var(--accent)]"
                />
                <span className="min-w-0">
                  <span className="block text-sm text-app">{t(option.labelKey)}</span>
                  <span className="block text-xs text-muted">{t(option.hintKey)}</span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-accent px-4 py-2.5 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60"
        >
          {submitting ? t('projects.creating') : t('projects.create')}
        </button>
      </form>
    </div>
  );
}
