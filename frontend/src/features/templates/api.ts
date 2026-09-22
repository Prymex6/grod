import { getJson, patchJson, postJson, sendDelete } from '../../lib/api';

export type OfferingKind = 'template' | 'application';

export interface Offering {
  slug: string;
  title: string;
  description: string;
  kind: OfferingKind;
  author: string;
  branch: string;
  image: string;
  published: boolean;
  taken: number;
  createdAt: string;
}

export interface Taken {
  kind: OfferingKind;
  address: string;
}

const base = '/market';
const path = (slug: string): string => `${base}/${encodeURIComponent(slug)}`;

export const fetchOfferings = (signal?: AbortSignal): Promise<Offering[]> =>
  getJson<Offering[]>(base, signal);

export const fetchMine = (signal?: AbortSignal): Promise<Offering[]> =>
  getJson<Offering[]>(`${base}/mine`, signal);

export const publishOffering = (values: {
  slug: string;
  title: string;
  description: string;
  kind: OfferingKind;
  owner: string;
  project: string;
  image: string;
}): Promise<Offering> => postJson<Offering>(base, values);

export const takeTemplate = (
  slug: string,
  values: { slug: string; name: string },
): Promise<Taken> => postJson<Taken>(`${path(slug)}/take-template`, values);

export const takeApplication = (slug: string, name: string): Promise<Taken> =>
  postJson<Taken>(`${path(slug)}/take-application`, { name });

export const setPublished = (slug: string, published: boolean): Promise<Offering> =>
  patchJson<Offering>(`${path(slug)}?published=${String(published)}`, {});

export const deleteOffering = (slug: string): Promise<void> => sendDelete(path(slug));
