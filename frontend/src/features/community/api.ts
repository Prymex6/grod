import { getJson, patchJson, postJson, sendDelete } from '../../lib/api';
import type { Project, Visibility } from '../projects/api';

export type GroupRole = 'guest' | 'developer' | 'maintainer' | 'owner';

export interface Group {
  id: string;
  slug: string;
  name: string;
  description: string;
  visibility: Visibility;
  createdAt: string;
  role: GroupRole | null;
  memberCount: number;
}

export interface GroupMember {
  login: string;
  displayName: string;
  role: GroupRole;
  createdAt: string;
}

const base = (slug: string): string => `/groups/${encodeURIComponent(slug)}`;

export const fetchGroups = (signal?: AbortSignal): Promise<Group[]> =>
  getJson<Group[]>('/groups', signal);

export const fetchGroup = (slug: string, signal?: AbortSignal): Promise<Group> =>
  getJson<Group>(base(slug), signal);

export const createGroup = (group: {
  slug: string;
  name: string;
  description: string;
  visibility: Visibility;
}): Promise<Group> => postJson<Group>('/groups', group);

export const changeGroup = (
  slug: string,
  changes: { name?: string; description?: string; visibility?: Visibility },
): Promise<Group> => patchJson<Group>(base(slug), changes);

export const deleteGroup = (slug: string): Promise<void> => sendDelete(base(slug));

export const fetchGroupProjects = (slug: string, signal?: AbortSignal): Promise<Project[]> =>
  getJson<Project[]>(`${base(slug)}/projects`, signal);

export const fetchGroupMembers = (slug: string, signal?: AbortSignal): Promise<GroupMember[]> =>
  getJson<GroupMember[]>(`${base(slug)}/members`, signal);

export const addGroupMember = (
  slug: string,
  member: { login: string; role: GroupRole },
): Promise<GroupMember> => postJson<GroupMember>(`${base(slug)}/members`, member);

export const removeGroupMember = (slug: string, login: string): Promise<void> =>
  sendDelete(`${base(slug)}/members/${encodeURIComponent(login)}`);
