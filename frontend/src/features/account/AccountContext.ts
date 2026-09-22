import { createContext } from 'react';

import type { Account } from '../auth/api';

/** The signed-in account, or null while it is still being loaded. */
export const AccountContext = createContext<Account | null>(null);
