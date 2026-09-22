import { postJson } from '../../lib/api';

export interface Account {
  id: string;
  email: string;
  login: string;
  displayName: string;
  totpEnabled: boolean;
  createdAt: string;
}

export interface SignedIn {
  status: 'signed_in';
  account: Account;
}

export interface TotpRequired {
  status: 'totp_required';
  pendingToken: string;
}

export type LoginResult = SignedIn | TotpRequired;

export const signIn = (email: string, password: string): Promise<LoginResult> =>
  postJson<LoginResult>('/auth/login', { email, password });

export const signInWithCode = (pendingToken: string, code: string): Promise<SignedIn> =>
  postJson<SignedIn>('/auth/login/totp', { pendingToken, code });

export const signOut = async (): Promise<void> => {
  await postJson<undefined>('/auth/logout');
};
