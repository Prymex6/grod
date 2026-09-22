import { useCallback, useEffect, useState } from 'react';

import { getJson } from '../../lib/api';

interface Health {
  status: 'ok';
  instance: string;
  version: string;
}

export type HealthState =
  { kind: 'loading' } | { kind: 'ready'; health: Health } | { kind: 'unavailable' };

interface InstanceHealth {
  state: HealthState;
  reload: () => void;
}

/** Reads the state of this instance from the platform API. */
export const useInstanceHealth = (): InstanceHealth => {
  const [state, setState] = useState<HealthState>({ kind: 'loading' });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();

    getJson<Health>('/health', controller.signal)
      .then((health) => {
        setState({ kind: 'ready', health });
      })
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        console.error('Health check failed', error);
        setState({ kind: 'unavailable' });
      });

    return () => {
      controller.abort();
    };
  }, [attempt]);

  const reload = useCallback(() => {
    setState({ kind: 'loading' });
    setAttempt((current) => current + 1);
  }, []);

  return { state, reload };
};
