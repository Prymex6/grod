import { getJson, postJson, sendDelete } from '../../lib/api';

export type WorkspaceState = 'stopped' | 'running' | 'failed';

export interface Workspace {
  id: string;
  name: string;
  /** The project this workspace works on, written owner/slug. */
  project: string;
  branch: string;
  image: string;
  commit: string;
  state: WorkspaceState;
  lastError: string;
  createdAt: string;
}

export interface Change {
  path: string;
  removed: boolean;
  size: number;
}

export interface Saved {
  commit: string;
  files: number;
}

const base = '/workspaces';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchWorkspaces = (signal?: AbortSignal): Promise<Workspace[]> =>
  getJson<Workspace[]>(base, signal);

export const createWorkspace = (values: {
  name: string;
  owner: string;
  slug: string;
  branch: string;
  image: string;
}): Promise<Workspace> => postJson<Workspace>(base, values);

export const startWorkspace = (name: string): Promise<Workspace> =>
  postJson<Workspace>(`${path(name)}/start`, {});

export const stopWorkspace = (name: string): Promise<Workspace> =>
  postJson<Workspace>(`${path(name)}/stop`, {});

export const fetchChanges = (name: string, signal?: AbortSignal): Promise<Change[]> =>
  getJson<Change[]>(`${path(name)}/changes`, signal);

export const saveWorkspace = (name: string, message: string): Promise<Saved> =>
  postJson<Saved>(`${path(name)}/save`, { message });

export const deleteWorkspace = (name: string): Promise<void> => sendDelete(path(name));

/** Where the terminal of one workspace listens. */
export const terminalUrl = (name: string): string => {
  const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
  return `${scheme}://${window.location.host}/api/v1${path(name)}/terminal`;
};
