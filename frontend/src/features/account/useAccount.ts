import { useContext } from 'react';

import type { Account } from '../auth/api';
import { AccountContext } from './AccountContext';

/** The signed-in account; null until the shell has loaded it. */
export const useAccount = (): Account | null => useContext(AccountContext);
