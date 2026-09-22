import { getJson, patchJson, postJson, sendDelete } from '../../lib/api';

export type CheckState = 'unknown' | 'up' | 'down';

export interface Check {
  id: string;
  name: string;
  url: string;
  intervalSeconds: number;
  expectedStatus: number;
  enabled: boolean;
  state: CheckState;
  lastCheckedAt: string | null;
  lastDurationMs: number | null;
  lastError: string;
  uptime: number;
  averageMs: number;
  createdAt: string;
}

export interface CheckResult {
  ok: boolean;
  statusCode: number | null;
  durationMs: number;
  error: string;
  createdAt: string;
}

const base = '/checks';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchChecks = (signal?: AbortSignal): Promise<Check[]> =>
  getJson<Check[]>(base, signal);

export const createCheck = (values: {
  name: string;
  url: string;
  intervalSeconds: number;
}): Promise<Check> => postJson<Check>(base, values);

export const changeCheck = (
  name: string,
  changes: { url?: string; intervalSeconds?: number; enabled?: boolean },
): Promise<Check> => patchJson<Check>(path(name), changes);

export const runCheck = (name: string): Promise<Check> => postJson<Check>(`${path(name)}/run`, {});

export const fetchResults = (name: string, signal?: AbortSignal): Promise<CheckResult[]> =>
  getJson<CheckResult[]>(`${path(name)}/results`, signal);

export const deleteCheck = (name: string): Promise<void> => sendDelete(path(name));
