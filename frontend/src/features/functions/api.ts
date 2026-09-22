import { getJson, patchJson, postJson, sendDelete } from '../../lib/api';

export type Runtime = 'python' | 'node';

export interface GrodFunction {
  id: string;
  name: string;
  runtime: Runtime;
  source: string;
  timeoutSeconds: number;
  memoryMb: number;
  calls: number;
  failures: number;
  lastCalledAt: string | null;
  lastDurationMs: number | null;
  lastError: string;
  createdAt: string;
}

export interface CallResult {
  ok: boolean;
  answer: unknown;
  output: string;
  error: string;
  durationMs: number;
  timedOut: boolean;
}

const base = '/functions';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchFunctions = (signal?: AbortSignal): Promise<GrodFunction[]> =>
  getJson<GrodFunction[]>(base, signal);

export const fetchFunction = (name: string, signal?: AbortSignal): Promise<GrodFunction> =>
  getJson<GrodFunction>(path(name), signal);

export const createFunction = (values: {
  name: string;
  runtime: Runtime;
  source: string;
}): Promise<GrodFunction> => postJson<GrodFunction>(base, values);

export const changeFunction = (
  name: string,
  changes: { source?: string; timeoutSeconds?: number; memoryMb?: number },
): Promise<GrodFunction> => patchJson<GrodFunction>(path(name), changes);

export const callFunction = (name: string, event: unknown): Promise<CallResult> =>
  postJson<CallResult>(`${path(name)}/call`, event);

export const deleteFunction = (name: string): Promise<void> => sendDelete(path(name));
