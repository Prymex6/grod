import { useRef, type ClipboardEvent, type KeyboardEvent, type ReactNode } from 'react';

interface OtpInputProps {
  value: readonly string[];
  onChange: (next: string[]) => void;
  label: string;
  digitLabel: (position: number) => string;
}

const onlyDigits = (text: string): string => text.replace(/\D/gu, '');

/** One box per digit, with arrow keys, backspace and pasting the whole code. */
export function OtpInput({ value, onChange, label, digitLabel }: OtpInputProps): ReactNode {
  const inputsRef = useRef<(HTMLInputElement | null)[]>([]);

  const focus = (index: number): void => {
    inputsRef.current[index]?.focus();
  };

  const setDigit = (index: number, raw: string): void => {
    const digit = onlyDigits(raw).slice(-1);
    const next = [...value];
    next[index] = digit;
    onChange(next);
    if (digit && index < value.length - 1) focus(index + 1);
  };

  const handleKeyDown = (index: number, event: KeyboardEvent<HTMLInputElement>): void => {
    const isEmpty = !value[index];
    if (event.key === 'Backspace' && isEmpty && index > 0) focus(index - 1);
    else if (event.key === 'ArrowLeft' && index > 0) focus(index - 1);
    else if (event.key === 'ArrowRight' && index < value.length - 1) focus(index + 1);
  };

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>): void => {
    event.preventDefault();
    const pasted = onlyDigits(event.clipboardData.getData('text')).slice(0, value.length);
    if (!pasted) return;
    const next = Array.from({ length: value.length }, (_, index) => pasted[index] ?? '');
    onChange(next);
    focus(Math.min(pasted.length, value.length - 1));
  };

  return (
    <div>
      <span className="mb-2 block text-sm font-medium text-app">{label}</span>
      <div className="flex justify-between gap-2">
        {value.map((digit, index) => (
          <input
            // The boxes have no identity beyond their position in the code.
            key={index}
            ref={(element) => {
              inputsRef.current[index] = element;
            }}
            type="text"
            inputMode="numeric"
            autoComplete="one-time-code"
            maxLength={1}
            value={digit}
            onChange={(event) => {
              setDigit(index, event.target.value);
            }}
            onKeyDown={(event) => {
              handleKeyDown(index, event);
            }}
            onPaste={handlePaste}
            aria-label={digitLabel(index + 1)}
            className="h-12 w-full rounded-lg border border-app bg-app text-center font-mono text-lg font-semibold text-app focus:border-accent focus:outline-none"
          />
        ))}
      </div>
    </div>
  );
}
