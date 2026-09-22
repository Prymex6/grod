import { getJson, postJson, sendDelete } from '../../lib/api';

/** The kinds of thing a permission can be about, as the API spells them. */
export type ResourceKind =
  | 'bucket'
  | 'application'
  | 'function'
  | 'database'
  | 'queue'
  | 'route'
  | 'check'
  | 'error_source'
  | 'api_doc';

export type Role = 'viewer' | 'operator' | 'admin';
export type SubjectKind = 'user' | 'group' | 'service';

export interface ServiceAccount {
  id: string;
  name: string;
  active: boolean;
  lastUsedAt: string | null;
  createdAt: string;
}

export interface NewServiceAccount extends ServiceAccount {
  /** Shown once, at creation, and never again. */
  token: string;
}

export interface Grant {
  id: string;
  resourceKind: ResourceKind;
  resourceId: string;
  subjectKind: SubjectKind;
  subjectId: string;
  subject: string;
  role: Role;
  createdAt: string;
}

/** Anything a permission can be given for, as every module lists it. */
export interface Resource {
  id: string;
  name: string;
}

/** Where each kind of resource is listed, so one page can reach them all. */
export const RESOURCE_PATHS: Record<ResourceKind, string> = {
  bucket: '/storage/buckets',
  application: '/apps',
  function: '/functions',
  database: '/databases',
  queue: '/queues',
  route: '/routes',
  check: '/checks',
  error_source: '/errors/sources',
  api_doc: '/apis',
};

const accounts = '/iam/service-accounts';
const grants = '/iam/grants';

export const fetchServiceAccounts = (signal?: AbortSignal): Promise<ServiceAccount[]> =>
  getJson<ServiceAccount[]>(accounts, signal);

export const createServiceAccount = (name: string): Promise<NewServiceAccount> =>
  postJson<NewServiceAccount>(accounts, { name });

export const deleteServiceAccount = (name: string): Promise<void> =>
  sendDelete(`${accounts}/${encodeURIComponent(name)}`);

export const fetchResources = (kind: ResourceKind, signal?: AbortSignal): Promise<Resource[]> =>
  getJson<Resource[]>(RESOURCE_PATHS[kind], signal);

export const fetchGrants = (
  kind: ResourceKind,
  resourceId: string,
  signal?: AbortSignal,
): Promise<Grant[]> =>
  getJson<Grant[]>(
    `${grants}?resourceKind=${kind}&resourceId=${encodeURIComponent(resourceId)}`,
    signal,
  );

export const writeGrant = (values: {
  resourceKind: ResourceKind;
  resourceId: string;
  subjectKind: SubjectKind;
  subject: string;
  role: Role;
}): Promise<Grant> => postJson<Grant>(grants, values);

export const revokeGrant = (grant: Grant): Promise<void> =>
  sendDelete(
    `${grants}?resourceKind=${grant.resourceKind}` +
      `&resourceId=${encodeURIComponent(grant.resourceId)}` +
      `&subjectKind=${grant.subjectKind}` +
      `&subjectId=${encodeURIComponent(grant.subjectId)}`,
  );
