import { useState } from 'react';

import { ApiError, NetworkError } from '../../lib/api';
import { signIn, signInWithCode, type Account } from './api';

export type SignInErrorKind =
  'invalidCredentials' | 'invalidCode' | 'tooManyAttempts' | 'network' | 'unknown';

interface SignInState {
  submitting: boolean;
  error: SignInErrorKind | null;
  pendingToken: string | null;
}

interface SignInActions {
  submitCredentials: (email: string, password: string) => Promise<void>;
  submitCode: (code: string) => Promise<void>;
  reset: () => void;
}

const HTTP_UNAUTHORIZED = 401;
const HTTP_TOO_MANY_REQUESTS = 429;

const classify = (error: unknown, onUnauthorized: SignInErrorKind): SignInErrorKind => {
  if (error instanceof NetworkError) return 'network';
  if (error instanceof ApiError) {
    if (error.status === HTTP_TOO_MANY_REQUESTS) return 'tooManyAttempts';
    if (error.status === HTTP_UNAUTHORIZED) return onUnauthorized;
  }
  return 'unknown';
};

/** Drives the two steps of signing in and reports what went wrong. */
export const useSignIn = (onSignedIn: (account: Account) => void): SignInState & SignInActions => {
  const [state, setState] = useState<SignInState>({
    submitting: false,
    error: null,
    pendingToken: null,
  });

  const run = async (
    action: () => Promise<void>,
    unauthorizedMeans: SignInErrorKind,
  ): Promise<void> => {
    setState((current) => ({ ...current, submitting: true, error: null }));
    try {
      await action();
    } catch (error) {
      setState((current) => ({
        ...current,
        submitting: false,
        error: classify(error, unauthorizedMeans),
      }));
    }
  };

  const submitCredentials = (email: string, password: string): Promise<void> =>
    run(async () => {
      const result = await signIn(email, password);
      if (result.status === 'totp_required') {
        setState({ submitting: false, error: null, pendingToken: result.pendingToken });
        return;
      }
      setState({ submitting: false, error: null, pendingToken: null });
      onSignedIn(result.account);
    }, 'invalidCredentials');

  const submitCode = (code: string): Promise<void> =>
    run(async () => {
      const { pendingToken } = state;
      if (pendingToken === null) throw new Error('No sign-in is waiting for a code');
      const result = await signInWithCode(pendingToken, code);
      setState({ submitting: false, error: null, pendingToken: null });
      onSignedIn(result.account);
    }, 'invalidCode');

  const reset = (): void => {
    setState({ submitting: false, error: null, pendingToken: null });
  };

  return { ...state, submitCredentials, submitCode, reset };
};
