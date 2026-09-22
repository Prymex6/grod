import { getJson, postJson, sendDelete, sendPutJson } from '../../lib/api';

export interface Site {
  branch: string;
  directory: string;
  enabled: boolean;
  publishedCommit: string | null;
  publishedAt: string | null;
  url: string;
}

const base = (owner: string, slug: string): string =>
  `/projects/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}/site`;

export const fetchSite = (owner: string, slug: string, signal?: AbortSignal): Promise<Site> =>
  getJson<Site>(base(owner, slug), signal);

export const configureSite = (
  owner: string,
  slug: string,
  site: { branch: string; directory: string; enabled: boolean },
): Promise<Site> => sendPutJson<Site>(base(owner, slug), site);

export const publishSite = (owner: string, slug: string): Promise<Site> =>
  postJson<Site>(`${base(owner, slug)}/publish`, {});

export const removeSite = (owner: string, slug: string): Promise<void> =>
  sendDelete(base(owner, slug));
