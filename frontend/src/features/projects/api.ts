import { getJson, postJson, sendDelete, sendDeleteJson, sendPut, sendPutJson } from '../../lib/api';

export type Visibility = 'private' | 'internal' | 'public';

export interface Access {
  read: boolean;
  write: boolean;
  manage: boolean;
  own: boolean;
}

export interface Project {
  id: string;
  ownerLogin: string;
  slug: string;
  name: string;
  description: string;
  visibility: Visibility;
  defaultBranch: string;
  empty: boolean;
  cloneUrl: string;
  createdAt: string;
  access: Access;
  stars: number;
  starred: boolean;
}

export interface Ref {
  name: string;
  commit: string;
}

export interface TreeEntry {
  name: string;
  path: string;
  type: 'blob' | 'tree';
  size: number | null;
}

export interface RepositoryFile {
  path: string;
  size: number;
  text: string | null;
  binary: boolean;
}

export interface SearchMatch {
  path: string;
  lineNumber: number;
  line: string;
}

export interface Commit {
  hash: string;
  authorName: string;
  authorEmail: string;
  authoredAt: string;
  subject: string;
}

export interface ProtectedBranch {
  id: string;
  pattern: string;
  createdAt: string;
}

export interface NewProject {
  slug: string;
  name: string;
  description: string;
  visibility: Visibility;
  /** Address of the group that is to own it; null means a personal project. */
  group?: string | null;
}

const base = (owner: string, slug: string): string =>
  `/projects/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}`;

const withParams = (path: string, params: Record<string, string | undefined>): string => {
  const query = new URLSearchParams();
  for (const [name, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') query.set(name, value);
  }
  const suffix = query.toString();
  return suffix ? `${path}?${suffix}` : path;
};

const encodePath = (path: string): string => path.split('/').map(encodeURIComponent).join('/');

export const fetchProjects = (signal?: AbortSignal): Promise<Project[]> =>
  getJson<Project[]>('/projects', signal);

export const createProject = (project: NewProject): Promise<Project> =>
  postJson<Project>('/projects', project);

export const fetchProject = (owner: string, slug: string, signal?: AbortSignal): Promise<Project> =>
  getJson<Project>(base(owner, slug), signal);

export const deleteProject = (owner: string, slug: string): Promise<void> =>
  sendDelete(base(owner, slug));

export const fetchBranches = (owner: string, slug: string, signal?: AbortSignal): Promise<Ref[]> =>
  getJson<Ref[]>(`${base(owner, slug)}/branches`, signal);

export const fetchTree = (
  owner: string,
  slug: string,
  options: { ref?: string; path?: string },
  signal?: AbortSignal,
): Promise<TreeEntry[]> =>
  getJson<TreeEntry[]>(
    withParams(`${base(owner, slug)}/tree`, { ref: options.ref, path: options.path }),
    signal,
  );

export const fetchFile = (
  owner: string,
  slug: string,
  options: { path: string; ref?: string },
  signal?: AbortSignal,
): Promise<RepositoryFile> =>
  getJson<RepositoryFile>(
    withParams(`${base(owner, slug)}/file`, { path: options.path, ref: options.ref }),
    signal,
  );

export interface CommitMade {
  commit: string;
  branch: string;
  path: string;
}

/** Write a file into a branch, making the commit that carries it. */
export const writeFile = (
  owner: string,
  slug: string,
  path: string,
  change: { content: string; message: string; branch: string; parentCommit: string | null },
): Promise<CommitMade> =>
  sendPutJson<CommitMade>(`${base(owner, slug)}/files/${encodePath(path)}`, change);

/** Take a file out of a branch, making the commit that does it. */
export const deleteFile = (
  owner: string,
  slug: string,
  path: string,
  change: { message: string; branch: string; parentCommit: string | null },
): Promise<CommitMade> =>
  sendDeleteJson<CommitMade>(
    withParams(`${base(owner, slug)}/files/${encodePath(path)}`, {
      branch: change.branch,
      message: change.message,
      parentCommit: change.parentCommit ?? undefined,
    }),
  );

export const fetchCommits = (
  owner: string,
  slug: string,
  options: { ref?: string; limit?: number },
  signal?: AbortSignal,
): Promise<Commit[]> =>
  getJson<Commit[]>(
    withParams(`${base(owner, slug)}/commits`, {
      ref: options.ref,
      limit: options.limit?.toString(),
    }),
    signal,
  );

export const fetchProtectedBranches = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<ProtectedBranch[]> =>
  getJson<ProtectedBranch[]>(`${base(owner, slug)}/protected-branches`, signal);

export const protectBranch = (
  owner: string,
  slug: string,
  pattern: string,
): Promise<ProtectedBranch> =>
  postJson<ProtectedBranch>(`${base(owner, slug)}/protected-branches`, { pattern });

export const unprotectBranch = (owner: string, slug: string, pattern: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/protected-branches/${encodeURIComponent(pattern)}`);

export const searchRepository = (
  owner: string,
  slug: string,
  options: { query: string; ref?: string },
  signal?: AbortSignal,
): Promise<SearchMatch[]> =>
  getJson<SearchMatch[]>(
    withParams(`${base(owner, slug)}/search`, { q: options.query, ref: options.ref }),
    signal,
  );

export interface Profile {
  login: string;
  displayName: string;
  createdAt: string;
  projects: Project[];
  starsGiven: number;
  starsReceived: number;
}

export const starProject = (owner: string, slug: string): Promise<void> =>
  sendPut(`${base(owner, slug)}/star`);

export const unstarProject = (owner: string, slug: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/star`);

export const fetchStarred = (signal?: AbortSignal): Promise<Project[]> =>
  getJson<Project[]>('/starred', signal);

export const fetchPublicProjects = (signal?: AbortSignal): Promise<Project[]> =>
  getJson<Project[]>('/projects/explore', signal);

export const fetchProfile = (login: string, signal?: AbortSignal): Promise<Profile> =>
  getJson<Profile>(`/users/${encodeURIComponent(login)}`, signal);
