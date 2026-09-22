import { getJson, postJson, sendDelete } from '../../lib/api';

export type RunState = 'pending' | 'running' | 'success' | 'failed' | 'canceled';

export interface Job {
  id: string;
  name: string;
  stage: string;
  state: RunState;
  image: string | null;
  script: string[];
  startedAt: string | null;
  finishedAt: string | null;
}

export interface Pipeline {
  id: string;
  number: number;
  ref: string;
  commit: string;
  commitSubject: string;
  state: RunState;
  createdAt: string;
  startedAt: string | null;
  finishedAt: string | null;
  jobs: Job[];
}

export interface JobLog {
  id: string;
  state: RunState;
  log: string;
}

export interface Runner {
  id: string;
  name: string;
  tags: string;
  active: boolean;
  createdAt: string;
  lastSeenAt: string | null;
}

export interface NewRunner extends Runner {
  token: string;
}

const base = (owner: string, slug: string): string =>
  `/projects/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}`;

export const fetchPipelines = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<Pipeline[]> => getJson<Pipeline[]>(`${base(owner, slug)}/pipelines`, signal);

export const fetchPipeline = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<Pipeline> =>
  getJson<Pipeline>(`${base(owner, slug)}/pipelines/${number.toString()}`, signal);

export const startPipeline = (owner: string, slug: string, ref: string): Promise<Pipeline> =>
  postJson<Pipeline>(`${base(owner, slug)}/pipelines`, { ref });

export const cancelPipeline = (owner: string, slug: string, number: number): Promise<Pipeline> =>
  postJson<Pipeline>(`${base(owner, slug)}/pipelines/${number.toString()}/cancel`, {});

export const fetchJobLog = (
  owner: string,
  slug: string,
  jobId: string,
  signal?: AbortSignal,
): Promise<JobLog> => getJson<JobLog>(`${base(owner, slug)}/jobs/${jobId}/log`, signal);

export const fetchRunners = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<Runner[]> => getJson<Runner[]>(`${base(owner, slug)}/runners`, signal);

export const registerRunner = (
  owner: string,
  slug: string,
  runner: { name: string; tags: string },
): Promise<NewRunner> => postJson<NewRunner>(`${base(owner, slug)}/runners`, runner);

export const removeRunner = (owner: string, slug: string, runnerId: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/runners/${runnerId}`);
