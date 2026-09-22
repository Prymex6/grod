import { getJson, sendDelete, sendPutJson } from '../../lib/api';

export interface Secret {
  name: string;
  masked: boolean;
  protected: boolean;
  createdAt: string;
}

export interface Package {
  id: string;
  name: string;
  version: string;
  filename: string;
  size: number;
  digest: string;
  createdAt: string;
  url: string;
}

export interface RegistryImage {
  tag: string;
  digest: string;
  size: number;
  createdAt: string;
  /** What to write after `docker pull`. */
  reference: string;
}

export interface Registry {
  images: RegistryImage[];
  blobs: number;
  bytes: number;
}

const base = (owner: string, slug: string): string =>
  `/projects/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}`;

export const fetchSecrets = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<Secret[]> => getJson<Secret[]>(`${base(owner, slug)}/secrets`, signal);

export const setSecret = (
  owner: string,
  slug: string,
  secret: { name: string; value: string; masked: boolean; protected: boolean },
): Promise<Secret> => sendPutJson<Secret>(`${base(owner, slug)}/secrets`, secret);

export const removeSecret = (owner: string, slug: string, name: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/secrets/${encodeURIComponent(name)}`);

export const fetchPackages = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<Package[]> => getJson<Package[]>(`${base(owner, slug)}/packages`, signal);

export const removePackage = (owner: string, slug: string, packageId: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/packages/${packageId}`);

export const fetchImages = (owner: string, slug: string, signal?: AbortSignal): Promise<Registry> =>
  getJson<Registry>(`${base(owner, slug)}/images`, signal);

export const removeImage = (owner: string, slug: string, tag: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/images/${encodeURIComponent(tag)}`);
