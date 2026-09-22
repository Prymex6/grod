import { useEffect, useState } from 'react';

import { ApiError } from '../../lib/api';
import type { Account } from '../auth/api';
import { fetchAccount } from '../settings/api';

const HTTP_UNAUTHORIZED = 401;

/**
 * The signed-in account. A visitor without a session is sent to Brama, which
 * is what guards every page inside the console shell.
 */
export const useCurrentAccount = (): Account | null => {
  const [account, setAccount] = useState<Account | null>(null);

  useEffect(() => {
    const controller = new AbortController();

    fetchAccount(controller.signal)
      .then(setAccount)
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        if (error instanceof ApiError && error.status === HTTP_UNAUTHORIZED) {
          window.location.assign('/login');
        }
      });

    return () => {
      controller.abort();
    };
  }, []);

  return account;
};
