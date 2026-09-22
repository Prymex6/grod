import { getJson, patchJson, postJson, sendDelete, sendPutJson } from '../../lib/api';

export type DocSource = 'uploaded' | 'url';

export interface Operation {
  method: string;
  path: string;
  summary: string;
  description: string;
  tags: string[];
}

export interface ApiDoc {
  id: string;
  name: string;
  source: DocSource;
  url: string;
  title: string;
  version: string;
  public: boolean;
  operations: number;
  fetchedAt: string | null;
  lastError: string;
  createdAt: string;
}

export interface ApiDocDetail extends ApiDoc {
  paths: Operation[];
}

const base = '/apis';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchDocs = (signal?: AbortSignal): Promise<ApiDoc[]> =>
  getJson<ApiDoc[]>(base, signal);

export const fetchDoc = (name: string, signal?: AbortSignal): Promise<ApiDocDetail> =>
  getJson<ApiDocDetail>(path(name), signal);

export const createDoc = (values: {
  name: string;
  document: string;
  url: string;
  public: boolean;
}): Promise<ApiDoc> => postJson<ApiDoc>(base, values);

export const replaceDocument = (name: string, document: string): Promise<ApiDoc> =>
  sendPutJson<ApiDoc>(`${path(name)}/document`, { document });

export const refreshDoc = (name: string): Promise<ApiDoc> =>
  postJson<ApiDoc>(`${path(name)}/refresh`, {});

export const setPublic = (name: string, isPublic: boolean): Promise<ApiDoc> =>
  patchJson<ApiDoc>(`${path(name)}?public=${String(isPublic)}`, {});

export const deleteDoc = (name: string): Promise<void> => sendDelete(path(name));
