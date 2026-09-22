import { AlertCircle } from 'lucide-react';
import type { ReactNode } from 'react';

/** Message shown above a form when an action failed. */
export function ErrorBanner({ message }: { message: string }): ReactNode {
  return (
    <p
      role="alert"
      className="mb-4 flex items-start gap-2 rounded-lg bg-error-subtle p-3 text-sm text-error"
    >
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
      {message}
    </p>
  );
}
