import { getJson, postJson, sendDelete } from '../../lib/api';

export type RouteTarget = 'application' | 'address';

export interface Route {
  id: string;
  name: string;
  targetKind: RouteTarget;
  target: string;
  public: boolean;
  url: string;
  createdAt: string;
}

const base = '/routes';

export const fetchRoutes = (signal?: AbortSignal): Promise<Route[]> =>
  getJson<Route[]>(base, signal);

export const createRoute = (values: {
  name: string;
  targetKind: RouteTarget;
  target: string;
  public: boolean;
}): Promise<Route> => postJson<Route>(base, values);

export const deleteRoute = (name: string): Promise<void> =>
  sendDelete(`${base}/${encodeURIComponent(name)}`);
