import { getJson, patchJson, postJson, sendDelete } from '../../lib/api';

export type BucketAccess = 'private' | 'public';

export interface Bucket {
  id: string;
  name: string;
  access: BucketAccess;
  createdAt: string;
  objects: number;
  bytes: number;
}

export interface StoredObject {
  key: string;
  size: number;
  contentType: string;
  digest: string;
  createdAt: string;
  url: string;
}

const base = '/storage/buckets';

const bucketPath = (name: string): string => `${base}/${encodeURIComponent(name)}`;

/** Each part of a key is escaped on its own, so the slashes survive. */
const keyPath = (key: string): string => key.split('/').map(encodeURIComponent).join('/');

export const fetchBuckets = (signal?: AbortSignal): Promise<Bucket[]> =>
  getJson<Bucket[]>(base, signal);

export const fetchBucket = (name: string, signal?: AbortSignal): Promise<Bucket> =>
  getJson<Bucket>(bucketPath(name), signal);

export const createBucket = (bucket: { name: string; access: BucketAccess }): Promise<Bucket> =>
  postJson<Bucket>(base, bucket);

export const changeBucket = (name: string, access: BucketAccess): Promise<Bucket> =>
  patchJson<Bucket>(bucketPath(name), { access });

export const deleteBucket = (name: string): Promise<void> => sendDelete(bucketPath(name));

export const fetchObjects = (
  name: string,
  options: { prefix?: string } = {},
  signal?: AbortSignal,
): Promise<StoredObject[]> => {
  const query = options.prefix ? `?prefix=${encodeURIComponent(options.prefix)}` : '';
  return getJson<StoredObject[]>(`${bucketPath(name)}/objects${query}`, signal);
};

export const deleteObject = (name: string, key: string): Promise<void> =>
  sendDelete(`${bucketPath(name)}/objects/${keyPath(key)}`);

/** Uploads a file the browser picked, keeping its type. */
export const uploadObject = async (name: string, key: string, file: File): Promise<void> => {
  const response = await fetch(`/api/v1${bucketPath(name)}/objects/${keyPath(key)}`, {
    method: 'PUT',
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
    body: file,
  });
  if (!response.ok) throw new Error(`Upload failed with status ${String(response.status)}`);
};
