import { getJson, postJson, sendDelete } from '../../lib/api';

export type Level = 'info' | 'warning' | 'error' | 'fatal';

export interface Source {
  id: string;
  name: string;
  key: string;
  issues: number;
  unresolved: number;
  reports: number;
  createdAt: string;
}

export interface Issue {
  id: string;
  kind: string;
  message: string;
  culprit: string;
  level: Level;
  count: number;
  resolved: boolean;
  firstSeenAt: string;
  lastSeenAt: string;
}

export interface Report {
  message: string;
  stack: string;
  environment: string;
  release: string;
  context: Record<string, unknown>;
  createdAt: string;
}

const base = '/errors/sources';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchSources = (signal?: AbortSignal): Promise<Source[]> =>
  getJson<Source[]>(base, signal);

export const createSource = (name: string): Promise<Source> => postJson<Source>(base, { name });

export const deleteSource = (name: string): Promise<void> => sendDelete(path(name));

export const fetchIssues = (
  name: string,
  options: { resolved?: boolean } = {},
  signal?: AbortSignal,
): Promise<Issue[]> => {
  const query = options.resolved === undefined ? '' : `?resolved=${String(options.resolved)}`;
  return getJson<Issue[]>(`${path(name)}/issues${query}`, signal);
};

export const fetchReports = (
  name: string,
  issueId: string,
  signal?: AbortSignal,
): Promise<Report[]> => getJson<Report[]>(`${path(name)}/issues/${issueId}/reports`, signal);

export const resolveIssue = (name: string, issueId: string, resolved: boolean): Promise<Issue> =>
  postJson<Issue>(`${path(name)}/issues/${issueId}/resolve?resolved=${String(resolved)}`, {});
