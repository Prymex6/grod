import {
  startAuthentication,
  startRegistration,
  type PublicKeyCredentialCreationOptionsJSON,
  type PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser';

import { getJson, postJson, sendDelete } from '../../lib/api';
import type { Account, SignedIn } from '../auth/api';

export interface Passkey {
  id: string;
  label: string;
  createdAt: string;
  lastUsedAt: string | null;
}

export interface Authorization {
  clientId: string;
  name: string;
  scopes: string[];
  grantedAt: string;
}

export interface AccessToken {
  id: string;
  name: string;
  scopes: string[];
  createdAt: string;
  expiresAt: string | null;
  lastUsedAt: string | null;
}

interface NewAccessToken extends AccessToken {
  value: string;
}

export interface SshKey {
  id: string;
  name: string;
  algorithm: string;
  fingerprint: string;
  createdAt: string;
  lastUsedAt: string | null;
}

export interface SessionEntry {
  createdAt: string;
  userAgent: string;
  current: boolean;
}

interface TotpEnrollment {
  secret: string;
  provisioningUri: string;
}

interface RegistrationOptions {
  handle: string;
  options: PublicKeyCredentialCreationOptionsJSON;
}

interface AuthenticationOptions {
  handle: string;
  options: PublicKeyCredentialRequestOptionsJSON;
}

export const fetchAccount = (signal?: AbortSignal): Promise<Account> =>
  getJson<Account>('/auth/me', signal);

export const startTotpEnrollment = (): Promise<TotpEnrollment> =>
  postJson<TotpEnrollment>('/auth/totp/setup');

export const confirmTotpEnrollment = (code: string): Promise<void> =>
  postJson<undefined>('/auth/totp/confirm', { code });

export const disableTotp = (): Promise<void> => postJson<undefined>('/auth/totp/disable');

export const fetchPasskeys = (signal?: AbortSignal): Promise<Passkey[]> =>
  getJson<Passkey[]>('/auth/passkeys', signal);

export const removePasskey = (id: string): Promise<void> => sendDelete(`/auth/passkeys/${id}`);

/** Creates a passkey in the browser and registers it with Brama. */
export const addPasskey = async (label: string): Promise<Passkey> => {
  const { handle, options } = await postJson<RegistrationOptions>(
    '/auth/passkeys/register/options',
  );
  const credential = await startRegistration({ optionsJSON: options });
  return postJson<Passkey>('/auth/passkeys/register', { handle, credential, label });
};

/** Signs in with a passkey the browser already holds. */
export const signInWithPasskey = async (): Promise<SignedIn> => {
  const { handle, options } = await postJson<AuthenticationOptions>('/auth/passkeys/login/options');
  const credential = await startAuthentication({ optionsJSON: options });
  return postJson<SignedIn>('/auth/passkeys/login', { handle, credential });
};

export const fetchAuthorizations = (signal?: AbortSignal): Promise<Authorization[]> =>
  getJson<Authorization[]>('/oauth/authorizations', signal);

export const revokeAuthorization = (clientId: string): Promise<void> =>
  sendDelete(`/oauth/authorizations/${clientId}`);

export const fetchTokens = (signal?: AbortSignal): Promise<AccessToken[]> =>
  getJson<AccessToken[]>('/tokens', signal);

export const createToken = (token: { name: string; scopes: string[] }): Promise<NewAccessToken> =>
  postJson<NewAccessToken>('/tokens', token);

export const removeToken = (id: string): Promise<void> => sendDelete(`/tokens/${id}`);

export const fetchSshKeys = (signal?: AbortSignal): Promise<SshKey[]> =>
  getJson<SshKey[]>('/ssh-keys', signal);

export const addSshKey = (key: { name: string; publicKey: string }): Promise<SshKey> =>
  postJson<SshKey>('/ssh-keys', key);

export const removeSshKey = (id: string): Promise<void> => sendDelete(`/ssh-keys/${id}`);

export const fetchSessions = (signal?: AbortSignal): Promise<SessionEntry[]> =>
  getJson<SessionEntry[]>('/auth/sessions', signal);

export const logoutOtherSessions = (): Promise<{ closed: number }> =>
  postJson<{ closed: number }>('/auth/sessions/others/logout');

export interface Limits {
  storageBytes: number;
  buckets: number;
  applications: number;
  functions: number;
  databases: number;
  queues: number;
  workspaces: number;
}

export interface Usage {
  storageBytes: number;
  files: number;
  packages: number;
  layers: number;
  buckets: number;
  applications: number;
  functions: number;
  databases: number;
  queues: number;
  workspaces: number;
  limits: Limits;
}

export const fetchUsage = (signal?: AbortSignal): Promise<Usage> =>
  getJson<Usage>('/account/usage', signal);
