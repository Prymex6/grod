import { getJson, postJson, sendDelete } from '../../lib/api';

export type AppState = 'stopped' | 'running' | 'failed';

export interface Application {
  id: string;
  name: string;
  image: string;
  command: string;
  environment: Record<string, string>;
  port: number | null;
  hostPort: number | null;
  memoryMb: number;
  cpus: number;
  state: AppState;
  lastError: string;
  createdAt: string;
  url: string | null;
}

export interface NewApplication {
  name: string;
  image: string;
  command: string;
  environment: Record<string, string>;
  port: number | null;
  memoryMb: number;
  cpus: number;
}

const base = '/apps';
const appPath = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchApplications = (signal?: AbortSignal): Promise<Application[]> =>
  getJson<Application[]>(base, signal);

export const fetchApplication = (name: string, signal?: AbortSignal): Promise<Application> =>
  getJson<Application>(appPath(name), signal);

export const fetchEngine = (signal?: AbortSignal): Promise<{ available: boolean }> =>
  getJson<{ available: boolean }>(`${base}/engine`, signal);

export const createApplication = (application: NewApplication): Promise<Application> =>
  postJson<Application>(base, application);

export const startApplication = (name: string): Promise<Application> =>
  postJson<Application>(`${appPath(name)}/start`, {});

export const stopApplication = (name: string): Promise<Application> =>
  postJson<Application>(`${appPath(name)}/stop`, {});

export const fetchApplicationLog = (name: string, signal?: AbortSignal): Promise<{ log: string }> =>
  getJson<{ log: string }>(`${appPath(name)}/logs`, signal);

export const deleteApplication = (name: string): Promise<void> => sendDelete(appPath(name));
