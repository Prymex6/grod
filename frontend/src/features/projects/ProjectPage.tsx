import { Building2, GitBranch, Globe, Loader2, Lock } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useParams, useSearchParams } from 'react-router';

import { CopyButton } from '../../components/ui/CopyButton';
import type { TranslationKey } from '../../i18n/keys';
import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { useAccount } from '../account/useAccount';
import { IssueDetail } from '../collaboration/IssueDetail';
import { IssueList } from '../collaboration/IssueList';
import { MergeRequestDetail } from '../collaboration/MergeRequestDetail';
import { MergeRequestList } from '../collaboration/MergeRequestList';
import { PipelineDetail } from '../ci/PipelineDetail';
import { PipelineList } from '../ci/PipelineList';
import { RunnersSection } from '../ci/RunnersSection';
import { ImageList } from '../artifacts/ImageList';
import { PackageList } from '../artifacts/PackageList';
import { FindingList } from '../scanning/FindingList';
import { SecretsSection } from '../artifacts/SecretsSection';
import { SiteSection } from '../pages/SiteSection';
import { MembersSection } from '../collaboration/MembersSection';
import { CommitList } from './CommitList';
import { EmptyRepository } from './EmptyRepository';
import { ProjectSettings } from './ProjectSettings';
import { RepositoryBrowser } from './RepositoryBrowser';
import { RepositorySearch } from './RepositorySearch';
import { StarButton } from './StarButton';
import { fetchBranches, fetchProject, type Project, type Ref, type Visibility } from './api';

const VISIBILITY_ICON = {
  private: Lock,
  internal: Building2,
  public: Globe,
} as const satisfies Record<Visibility, typeof Lock>;

const VISIBILITY_KEY = {
  private: 'projects.visibility.private',
  internal: 'projects.visibility.internal',
  public: 'projects.visibility.public',
} as const satisfies Record<Visibility, string>;

type Tab =
  | 'code'
  | 'commits'
  | 'search'
  | 'issues'
  | 'merges'
  | 'pipelines'
  | 'packages'
  | 'security'
  | 'settings';

const TAB_KEYS = {
  code: 'project.tab.code',
  commits: 'project.tab.commits',
  issues: 'project.tab.issues',
  merges: 'project.tab.mergeRequests',
  pipelines: 'project.tab.pipelines',
  packages: 'project.tab.packages',
  security: 'project.tab.security',
  search: 'project.tab.search',
  settings: 'project.tab.settings',
} as const satisfies Record<Tab, TranslationKey>;

/** One project: its repository, branches and history. */
export function ProjectPage(): ReactNode {
  const { t } = useTranslation();
  const { owner = '', slug = '' } = useParams();
  const [params, setParams] = useSearchParams();
  const account = useAccount();
  const [project, setProject] = useState<Project | null>(null);
  const [branches, setBranches] = useState<Ref[]>([]);
  const [failed, setFailed] = useState(false);
  // Bumped after a commit made here, so the browser reads the new tree.
  const [reloads, setReloads] = useState(0);

  const path = params.get('path') ?? '';
  const requested = params.get('tab');
  // The API says what this account may do; the owner is only the usual case.
  const mayManage = project?.access.manage ?? false;
  const mayWrite = project?.access.write ?? false;
  const tab: Tab = ((): Tab => {
    if (
      requested === 'commits' ||
      requested === 'search' ||
      requested === 'issues' ||
      requested === 'merges' ||
      requested === 'pipelines' ||
      requested === 'packages'
    )
      return requested;
    if (requested === 'security' && mayWrite) return 'security';
    if (requested === 'settings' && mayManage) return 'settings';
    return 'code';
  })();
  // The tabs somebody sees follow what they may do in the project.
  const visibleTabs: Tab[] = [
    'code',
    'commits',
    'search',
    'issues',
    'merges',
    'pipelines',
    'packages',
    ...(mayWrite ? (['security'] as const) : []),
    ...(mayManage ? (['settings'] as const) : []),
  ];
  const reference = params.get('ref') ?? project?.defaultBranch ?? '';
  // Files are edited on a branch, so a tag or a commit shows read-only.
  const branch = branches.find((item) => item.name === reference) ?? null;
  const editableBranch =
    mayWrite && branch !== null ? { name: branch.name, commit: branch.commit } : null;
  const numberIn = (name: string): number | null => {
    const value = params.get(name);
    return value === null || Number.isNaN(Number(value)) ? null : Number(value);
  };
  const issueNumber = numberIn('issue');
  const mergeNumber = numberIn('merge');
  const pipelineNumber = numberIn('pipeline');

  useEffect(() => {
    const controller = new AbortController();

    fetchProject(owner, slug, controller.signal)
      .then((found) => {
        setProject(found);
        return fetchBranches(owner, slug, controller.signal);
      })
      .then(setBranches)
      .catch(() => {
        if (!controller.signal.aborted) setFailed(true);
      });

    return () => {
      controller.abort();
    };
  }, [owner, slug]);

  const change = (changes: Record<string, string | null>): void => {
    const next = new URLSearchParams(params);
    for (const [name, value] of Object.entries(changes)) {
      if (value === null) next.delete(name);
      else next.set(name, value);
    }
    setParams(next);
  };

  if (failed) {
    return (
      <div className="p-4 sm:p-6">
        <ErrorBanner message={t('project.error.notFound')} />
      </div>
    );
  }

  if (project === null) {
    return (
      <p className="flex items-center gap-2 p-4 text-sm text-muted sm:p-6">
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />
        {t('project.loading')}
      </p>
    );
  }

  const VisibilityIcon = VISIBILITY_ICON[project.visibility];

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div className="space-y-2">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="font-mono text-2xl font-semibold tracking-tight text-app">
            <Link to={`/${project.ownerLogin}`} className="hover:text-accent">
              {project.ownerLogin}
            </Link>
            /{project.slug}
          </h1>
          <span className="flex items-center gap-1 rounded-full bg-surface-raised px-2 py-0.5 text-xs text-muted">
            <VisibilityIcon className="h-3 w-3" aria-hidden="true" />
            {t(VISIBILITY_KEY[project.visibility])}
          </span>
        </div>
        {project.description !== '' && <p className="text-sm text-muted">{project.description}</p>}
        <div className="flex flex-wrap items-center gap-2">
          <code className="truncate rounded-lg border border-app bg-app px-2 py-1 font-mono text-xs text-muted">
            {project.cloneUrl}
          </code>
          <CopyButton value={project.cloneUrl} label={t('project.copyCloneUrl')} />
          {account !== null && <StarButton key={project.id} project={project} />}
        </div>
      </div>

      {project.empty && tab === 'code' ? (
        <EmptyRepository project={project} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <GitBranch className="h-4 w-4 text-muted" aria-hidden="true" />
              <label htmlFor="branch" className="sr-only">
                {t('project.branch')}
              </label>
              <select
                id="branch"
                value={reference}
                onChange={(event) => {
                  change({ ref: event.target.value });
                }}
                className="rounded-lg border border-app bg-surface px-2 py-1.5 font-mono text-sm text-app focus:border-accent focus:outline-none"
              >
                {branches.map((branch) => (
                  <option key={branch.name} value={branch.name}>
                    {branch.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex gap-1 rounded-lg border border-app bg-surface p-1">
              {visibleTabs.map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => {
                    change({ tab: item, path: null });
                  }}
                  aria-pressed={tab === item}
                  className={`rounded-md px-2.5 py-1 text-xs font-medium ${
                    tab === item
                      ? 'bg-accent text-accent-contrast'
                      : 'text-muted hover:bg-surface-raised hover:text-app'
                  }`}
                >
                  {t(TAB_KEYS[item])}
                </button>
              ))}
            </div>
          </div>

          {/* The key remounts the view when the revision or path changes. */}
          {tab === 'code' && (
            <RepositoryBrowser
              key={`${reference}:${path}:${reloads.toString()}`}
              project={project}
              reference={reference}
              path={path}
              editableBranch={editableBranch}
              onChanged={(written) => {
                setReloads((count) => count + 1);
                change({ path: written === '' ? null : written });
              }}
            />
          )}
          {tab === 'commits' && (
            <CommitList key={reference} project={project} reference={reference} />
          )}
          {tab === 'search' && <RepositorySearch project={project} reference={reference} />}
          {tab === 'issues' &&
            (issueNumber === null ? (
              <IssueList
                project={project}
                signedIn={account !== null}
                onOpenIssue={(number) => {
                  change({ issue: number.toString() });
                }}
              />
            ) : (
              <IssueDetail
                key={issueNumber}
                project={project}
                number={issueNumber}
                signedIn={account !== null}
                onBack={() => {
                  change({ issue: null });
                }}
              />
            ))}
          {tab === 'merges' &&
            (mergeNumber === null ? (
              <MergeRequestList
                project={project}
                branches={branches}
                mayOpen={mayWrite}
                onOpenRequest={(number) => {
                  change({ merge: number.toString() });
                }}
              />
            ) : (
              <MergeRequestDetail
                key={mergeNumber}
                project={project}
                number={mergeNumber}
                signedIn={account !== null}
                mayMerge={mayWrite}
                login={account?.login ?? null}
                onBack={() => {
                  change({ merge: null });
                }}
                onOpen={(other) => {
                  change({ merge: other.toString() });
                }}
              />
            ))}
          {tab === 'pipelines' &&
            (pipelineNumber === null ? (
              <PipelineList
                project={project}
                reference={reference}
                mayRun={mayWrite}
                onOpenPipeline={(number) => {
                  change({ pipeline: number.toString() });
                }}
              />
            ) : (
              <PipelineDetail
                key={pipelineNumber}
                project={project}
                number={pipelineNumber}
                mayRun={mayWrite}
                onBack={() => {
                  change({ pipeline: null });
                }}
              />
            ))}
          {tab === 'packages' && (
            <div className="space-y-8">
              <ImageList project={project} mayRemove={mayManage} />
              <PackageList project={project} mayRemove={mayManage} />
            </div>
          )}
          {tab === 'security' && <FindingList project={project} />}
          {tab === 'settings' && (
            <div className="space-y-10">
              <MembersSection project={project} />
              <RunnersSection project={project} />
              <SiteSection project={project} branches={branches} />
              <SecretsSection project={project} />
              <ProjectSettings project={project} />
            </div>
          )}
        </>
      )}
    </div>
  );
}
