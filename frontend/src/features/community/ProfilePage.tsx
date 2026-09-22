import { CalendarDays, FolderGit2, Loader2, Star } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { useParams } from 'react-router';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import type { TranslationKey } from '../../i18n/keys';
import { ProjectList } from '../projects/ProjectList';
import { fetchProfile, type Profile } from '../projects/api';

interface CountProps {
  icon: typeof Star;
  labelKey: TranslationKey;
  value: number;
}

/** One number of the profile, such as how many stars the account received. */
function Count({ icon: Icon, labelKey, value }: CountProps): ReactNode {
  const { t } = useTranslation();
  return (
    <div className="flex items-center gap-2 rounded-xl border border-app bg-surface px-3 py-2 shadow-app-sm">
      <Icon className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
      <span className="text-sm text-app">{value}</span>
      <span className="text-xs text-muted">{t(labelKey)}</span>
    </div>
  );
}

/** The public page of an account: who it is and what it works on. */
export function ProfilePage(): ReactNode {
  const { t, i18n } = useTranslation();
  const { login = '' } = useParams();
  const [profile, setProfile] = useState<Profile | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchProfile(login, controller.signal)
      .then(setProfile)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });
    return () => {
      controller.abort();
    };
  }, [login]);

  if (failed) {
    return (
      <div className="p-4 sm:p-6">
        <ErrorBanner message={t('profile.error.notFound')} />
      </div>
    );
  }

  if (profile === null) {
    return (
      <p className="flex items-center gap-2 p-4 text-sm text-muted sm:p-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('profile.loading')}
      </p>
    );
  }

  const joined = new Date(profile.createdAt).toLocaleDateString(i18n.resolvedLanguage ?? 'pl');

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="flex flex-wrap items-center gap-4">
        <span
          className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-accent-subtle text-2xl font-semibold text-accent"
          aria-hidden="true"
        >
          {profile.displayName.slice(0, 1).toUpperCase()}
        </span>
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold tracking-tight text-app">{profile.displayName}</h1>
          <p className="font-mono text-sm text-muted">{profile.login}</p>
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <Count icon={FolderGit2} labelKey="profile.projects" value={profile.projects.length} />
        <Count icon={Star} labelKey="profile.starsReceived" value={profile.starsReceived} />
        <Count icon={Star} labelKey="profile.starsGiven" value={profile.starsGiven} />
        <div className="flex items-center gap-2 rounded-xl border border-app bg-surface px-3 py-2 shadow-app-sm">
          <CalendarDays className="h-4 w-4 shrink-0 text-accent" aria-hidden="true" />
          <span className="text-xs text-muted">{t('profile.joined', { date: joined })}</span>
        </div>
      </div>

      {profile.projects.length === 0 ? (
        <p className="rounded-xl border border-app bg-surface px-4 py-6 text-center text-sm text-muted">
          {t('profile.noProjects')}
        </p>
      ) : (
        <ProjectList projects={profile.projects} />
      )}
    </div>
  );
}
