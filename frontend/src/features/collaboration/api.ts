import {
  getJson,
  patchJson,
  postJson,
  sendDelete,
  sendDeleteJson,
  sendPutJson,
} from '../../lib/api';

export type Role = 'guest' | 'developer' | 'maintainer';
export type IssueState = 'open' | 'closed';

export interface Author {
  login: string;
  displayName: string;
}

export interface Member {
  login: string;
  displayName: string;
  role: Role;
  createdAt: string;
}

export interface Issue {
  id: string;
  number: number;
  title: string;
  description: string;
  state: IssueState;
  author: Author;
  createdAt: string;
  updatedAt: string | null;
  closedAt: string | null;
}

export interface Comment {
  id: string;
  body: string;
  author: Author;
  createdAt: string;
}

const base = (owner: string, slug: string): string =>
  `/projects/${encodeURIComponent(owner)}/${encodeURIComponent(slug)}`;

export const fetchMembers = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<Member[]> => getJson<Member[]>(`${base(owner, slug)}/members`, signal);

export const addMember = (
  owner: string,
  slug: string,
  member: { login: string; role: Role },
): Promise<Member> => postJson<Member>(`${base(owner, slug)}/members`, member);

export const removeMember = (owner: string, slug: string, login: string): Promise<void> =>
  sendDelete(`${base(owner, slug)}/members/${encodeURIComponent(login)}`);

export const fetchIssues = (
  owner: string,
  slug: string,
  options: { state?: IssueState } = {},
  signal?: AbortSignal,
): Promise<Issue[]> => {
  const query = options.state === undefined ? '' : `?state=${options.state}`;
  return getJson<Issue[]>(`${base(owner, slug)}/issues${query}`, signal);
};

export const fetchIssue = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<Issue> => getJson<Issue>(`${base(owner, slug)}/issues/${number.toString()}`, signal);

export const openIssue = (
  owner: string,
  slug: string,
  issue: { title: string; description: string },
): Promise<Issue> => postJson<Issue>(`${base(owner, slug)}/issues`, issue);

export const changeIssue = (
  owner: string,
  slug: string,
  number: number,
  changes: { title?: string; description?: string; state?: IssueState },
): Promise<Issue> => patchJson<Issue>(`${base(owner, slug)}/issues/${number.toString()}`, changes);

export const fetchComments = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<Comment[]> =>
  getJson<Comment[]>(`${base(owner, slug)}/issues/${number.toString()}/comments`, signal);

export const addComment = (
  owner: string,
  slug: string,
  number: number,
  body: string,
): Promise<Comment> =>
  postJson<Comment>(`${base(owner, slug)}/issues/${number.toString()}/comments`, { body });

export const removeComment = (
  owner: string,
  slug: string,
  number: number,
  commentId: string,
): Promise<void> =>
  sendDelete(`${base(owner, slug)}/issues/${number.toString()}/comments/${commentId}`);

export type MergeState = 'open' | 'merged' | 'closed';

export interface MergeRequest {
  id: string;
  number: number;
  title: string;
  description: string;
  state: MergeState;
  sourceBranch: string;
  targetBranch: string;
  mergeCommit: string | null;
  author: Author;
  createdAt: string;
  updatedAt: string | null;
  mergedAt: string | null;
  closedAt: string | null;
}

export interface FileChange {
  path: string;
  additions: number;
  deletions: number;
  binary: boolean;
  patch: string;
}

export interface MergeCommit {
  hash: string;
  shortHash: string;
  subject: string;
  authorName: string;
  authoredAt: string;
}

export interface ReviewComment {
  id: string;
  body: string;
  filePath: string | null;
  lineNumber: number | null;
  author: Author;
  createdAt: string;
}

const mergeBase = (owner: string, slug: string): string => `${base(owner, slug)}/merge-requests`;

const one = (owner: string, slug: string, number: number): string =>
  `${mergeBase(owner, slug)}/${number.toString()}`;

export const fetchMergeRequests = (
  owner: string,
  slug: string,
  options: { state?: MergeState } = {},
  signal?: AbortSignal,
): Promise<MergeRequest[]> => {
  const query = options.state === undefined ? '' : `?state=${options.state}`;
  return getJson<MergeRequest[]>(`${mergeBase(owner, slug)}${query}`, signal);
};

export const fetchMergeRequest = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<MergeRequest> => getJson<MergeRequest>(one(owner, slug, number), signal);

export const openMergeRequest = (
  owner: string,
  slug: string,
  request: {
    title: string;
    description: string;
    sourceBranch: string;
    targetBranch: string;
  },
): Promise<MergeRequest> => postJson<MergeRequest>(mergeBase(owner, slug), request);

export const fetchChanges = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<FileChange[]> => getJson<FileChange[]>(`${one(owner, slug, number)}/changes`, signal);

export const fetchMergeCommits = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<MergeCommit[]> => getJson<MergeCommit[]>(`${one(owner, slug, number)}/commits`, signal);

export const mergeMergeRequest = (
  owner: string,
  slug: string,
  number: number,
): Promise<MergeRequest> => postJson<MergeRequest>(`${one(owner, slug, number)}/merge`, {});

export const closeMergeRequest = (
  owner: string,
  slug: string,
  number: number,
): Promise<MergeRequest> => postJson<MergeRequest>(`${one(owner, slug, number)}/close`, {});

export const reopenMergeRequest = (
  owner: string,
  slug: string,
  number: number,
): Promise<MergeRequest> => postJson<MergeRequest>(`${one(owner, slug, number)}/reopen`, {});

export const fetchReviewComments = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<ReviewComment[]> =>
  getJson<ReviewComment[]>(`${one(owner, slug, number)}/comments`, signal);

export const addReviewComment = (
  owner: string,
  slug: string,
  number: number,
  comment: { body: string; filePath?: string | null; lineNumber?: number | null },
): Promise<ReviewComment> =>
  postJson<ReviewComment>(`${one(owner, slug, number)}/comments`, comment);

export const removeReviewComment = (
  owner: string,
  slug: string,
  number: number,
  commentId: string,
): Promise<void> => sendDelete(`${one(owner, slug, number)}/comments/${commentId}`);

export type QueueState = 'waiting' | 'testing' | 'merged' | 'failed' | 'cancelled';

export interface QueuePlace {
  state: QueueState;
  /** 1 means next to go; 0 when the entry is no longer in line. */
  position: number;
  testedCommit: string;
  pipelineId: string | null;
  lastError: string;
  createdAt: string;
}

export interface QueueEntry extends QueuePlace {
  number: number;
  title: string;
}

export const fetchQueuePlace = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<QueuePlace | null> =>
  getJson<QueuePlace | null>(`${one(owner, slug, number)}/queue`, signal);

export const enterQueue = (owner: string, slug: string, number: number): Promise<QueuePlace> =>
  postJson<QueuePlace>(`${one(owner, slug, number)}/queue`, {});

export const leaveQueue = (owner: string, slug: string, number: number): Promise<void> =>
  sendDelete(`${one(owner, slug, number)}/queue`);

export const fetchMergeQueue = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<QueueEntry[]> => getJson<QueueEntry[]>(`${base(owner, slug)}/merge-queue`, signal);

export const fetchRequiredChecks = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<string[]> => getJson<string[]>(`${base(owner, slug)}/required-checks`, signal);

export const setRequiredChecks = (
  owner: string,
  slug: string,
  names: string[],
): Promise<string[]> => sendPutJson<string[]>(`${base(owner, slug)}/required-checks`, { names });

export interface Approval {
  login: string;
  displayName: string;
  commit: string;
  /** An approval given on older work says nothing about the work now. */
  stale: boolean;
}

export interface ApprovalState {
  given: Approval[];
  required: number;
  counted: number;
  missingOwners: string[];
  satisfied: boolean;
}

export interface MergeRules {
  requiredApprovals: number;
  requiredChecks: string[];
}

export const fetchApprovals = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<ApprovalState> =>
  getJson<ApprovalState>(`${one(owner, slug, number)}/approvals`, signal);

export const approveMergeRequest = (
  owner: string,
  slug: string,
  number: number,
): Promise<ApprovalState> => postJson<ApprovalState>(`${one(owner, slug, number)}/approve`, {});

export const revokeApproval = (
  owner: string,
  slug: string,
  number: number,
): Promise<ApprovalState> => sendDeleteJson<ApprovalState>(`${one(owner, slug, number)}/approve`);

export const fetchMergeRules = (
  owner: string,
  slug: string,
  signal?: AbortSignal,
): Promise<MergeRules> => getJson<MergeRules>(`${base(owner, slug)}/merge-rules`, signal);

export const setMergeRules = (
  owner: string,
  slug: string,
  rules: MergeRules,
): Promise<MergeRules> => sendPutJson<MergeRules>(`${base(owner, slug)}/merge-rules`, rules);

export interface Finding {
  path: string;
  line: number;
  column: number | null;
  /** The job that said it, which is how the console names the tool. */
  tool: string;
  message: string;
}

export const fetchFindings = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<Finding[]> => getJson<Finding[]>(`${one(owner, slug, number)}/findings`, signal);

export const applySuggestion = (
  owner: string,
  slug: string,
  number: number,
  commentId: string,
): Promise<MergeCommit> =>
  postJson<MergeCommit>(`${one(owner, slug, number)}/comments/${commentId}/apply`, {});

export interface StackStep {
  number: number;
  title: string;
  state: MergeState;
  sourceBranch: string;
  targetBranch: string;
  /** 1 is the bottom of the stack: the one that goes in first. */
  position: number;
}

export const fetchStack = (
  owner: string,
  slug: string,
  number: number,
  signal?: AbortSignal,
): Promise<StackStep[]> => getJson<StackStep[]>(`${one(owner, slug, number)}/stack`, signal);
