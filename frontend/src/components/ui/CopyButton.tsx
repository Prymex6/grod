import { Check, Copy } from 'lucide-react';
import { useState, type ReactNode } from 'react';

const FEEDBACK_MS = 1500;

/** Copies a value to the clipboard and says so for a moment. */
export function CopyButton({ value, label }: { value: string; label: string }): ReactNode {
  const [copied, setCopied] = useState(false);

  const copy = (): void => {
    navigator.clipboard
      .writeText(value)
      .then(() => {
        setCopied(true);
        setTimeout(() => {
          setCopied(false);
        }, FEEDBACK_MS);
      })
      .catch(() => {
        // Clipboard access can be blocked; the value stays visible anyway.
      });
  };

  return (
    <button
      type="button"
      onClick={copy}
      aria-label={label}
      className="flex h-8 w-8 items-center justify-center rounded-md text-muted hover:bg-surface-raised hover:text-app"
    >
      {copied ? (
        <Check className="h-4 w-4 text-success" aria-hidden="true" />
      ) : (
        <Copy className="h-4 w-4" aria-hidden="true" />
      )}
    </button>
  );
}
