import {
  Activity,
  Archive,
  BookOpen,
  Compass,
  FileCode2,
  FolderGit2,
  GitPullRequest,
  KeyRound,
  Globe,
  Hammer,
  ListChecks,
  Radar,
  Route,
  Send,
  Server,
  Shield,
  Store,
  Users,
  Vault,
  Wind,
  type LucideIcon,
} from 'lucide-react';

import type { TranslationKey } from './i18n/keys';

/** Module names are proper nouns and stay the same in every language. */
export const MODULE_NAMES = {
  accounts: 'Brama',
  ci: 'Kuźnia',
  pages: 'Witryna',
  artifacts: 'Skarbiec',
  apps: 'Osada',
  functions: 'Młyn',
  storage: 'Spichlerz',
  databases: 'Księgi',
  queues: 'Goniec',
  monitoring: 'Strażnica',
  routing: 'Drogowskaz',
  errors: 'Czujka',
  apidocs: 'Skryptorium',
  iam: 'Klucznik',
  workspaces: 'Warsztat',
  templates: 'Jarmark',
} as const;

export type ModuleId = keyof typeof MODULE_NAMES;

export interface CodeNavItem {
  labelKey: TranslationKey;
  icon: LucideIcon;
  /** Set once the page behind the entry exists. */
  to?: string;
}

export interface ModuleNavItem {
  id: ModuleId;
  descriptionKey: TranslationKey;
  icon: LucideIcon;
  /** Set once the page behind the module exists. */
  to?: string;
}

export const CODE_NAV: readonly CodeNavItem[] = [
  { labelKey: 'nav.projects', icon: FolderGit2, to: '/projects' },
  { labelKey: 'nav.groups', icon: Users, to: '/groups' },
  { labelKey: 'nav.mergeRequests', icon: GitPullRequest },
  { labelKey: 'nav.tasks', icon: ListChecks },
  { labelKey: 'nav.explore', icon: Compass, to: '/explore' },
];

export const CLOUD_NAV: readonly ModuleNavItem[] = [
  { id: 'accounts', descriptionKey: 'module.accounts.desc', icon: Shield },
  { id: 'ci', descriptionKey: 'module.ci.desc', icon: Hammer },
  { id: 'pages', descriptionKey: 'module.pages.desc', icon: Globe },
  { id: 'artifacts', descriptionKey: 'module.artifacts.desc', icon: Vault },
  { id: 'apps', descriptionKey: 'module.apps.desc', icon: Server, to: '/apps' },
  { id: 'functions', descriptionKey: 'module.functions.desc', icon: Wind, to: '/functions' },
  { id: 'storage', descriptionKey: 'module.storage.desc', icon: Archive, to: '/storage' },
  { id: 'databases', descriptionKey: 'module.databases.desc', icon: BookOpen, to: '/databases' },
  { id: 'queues', descriptionKey: 'module.queues.desc', icon: Send, to: '/queues' },
  { id: 'monitoring', descriptionKey: 'module.monitoring.desc', icon: Activity, to: '/checks' },
  { id: 'routing', descriptionKey: 'module.routing.desc', icon: Route, to: '/routes' },
  { id: 'errors', descriptionKey: 'module.errors.desc', icon: Radar, to: '/errors' },
  { id: 'apidocs', descriptionKey: 'module.apidocs.desc', icon: FileCode2, to: '/apis' },
  { id: 'iam', descriptionKey: 'module.iam.desc', icon: KeyRound, to: '/access' },
  { id: 'workspaces', descriptionKey: 'module.workspaces.desc', icon: Hammer, to: '/workspaces' },
  { id: 'templates', descriptionKey: 'module.templates.desc', icon: Store, to: '/market' },
];
