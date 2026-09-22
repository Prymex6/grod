import { getJson, postJson, sendDelete } from '../../lib/api';

export interface ManagedDatabase {
  id: string;
  name: string;
  engine: 'postgres';
  databaseName: string;
  roleName: string;
  host: string;
  port: number;
  sizeBytes: number;
  createdAt: string;
}

export interface DatabaseConnection {
  host: string;
  port: number;
  database: string;
  user: string;
  password: string;
  url: string;
}

const base = '/databases';
const path = (name: string): string => `${base}/${encodeURIComponent(name)}`;

export const fetchDatabases = (signal?: AbortSignal): Promise<ManagedDatabase[]> =>
  getJson<ManagedDatabase[]>(base, signal);

export const createDatabase = (name: string): Promise<ManagedDatabase> =>
  postJson<ManagedDatabase>(base, { name });

export const fetchConnection = (name: string, signal?: AbortSignal): Promise<DatabaseConnection> =>
  getJson<DatabaseConnection>(`${path(name)}/connection`, signal);

export const rotatePassword = (name: string): Promise<DatabaseConnection> =>
  postJson<DatabaseConnection>(`${path(name)}/rotate-password`, {});

export const deleteDatabase = (name: string): Promise<void> => sendDelete(path(name));
