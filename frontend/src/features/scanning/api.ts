import { getJson, patchJson, postJson } from '../../lib/api';

export type FindingState = 'open' | 'ignored' | 'fixed';

export interface Finding {
  id: string;
  /** The name of the rule that matched, e.g. "aws-access-key". */
  rule: string;
  /** False for rules that match anything shaped like a password. */
  certain: boolean;
  path: string;
  line: number;
  /** The line with the secret starred out; the value itself is never kept. */
  snippet: string;
  commit: string;
  state: FindingState;
  createdAt: string;
  lastSeenAt: string;
}

export interface ScanResult {
  commit: string;
  files: number;
  opened: number;
  closed: number;
  openTotal: number;
}

const base = (owner: string, slug: string): string =>
  `/projects/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}/findings`;

export const fetchFindings = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<Finding[]> => getJson<Finding[]>(base(owner, slug), signal);

export const scanNow = (owner: string, slug: string): Promise<ScanResult> =>
  postJson<ScanResult>(`${base(owner, slug)}/scan`, {});

export const setFindingState = (
  owner: string,
  slug: string,
  findingId: string,
  state: FindingState,
): Promise<Finding> => patchJson<Finding>(`${base(owner, slug)}/${findingId}`, { state });
