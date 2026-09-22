import { ShieldCheck, ShieldOff } from 'lucide-react';
import { QRCodeSVG } from 'qrcode.react';
import { useState, type ReactNode, type SyntheticEvent } from 'react';
import { useTranslation } from 'react-i18next';

import { ErrorBanner } from '../../components/ui/ErrorBanner';
import { OtpInput } from '../auth/OtpInput';
import { confirmTotpEnrollment, disableTotp, startTotpEnrollment } from './api';

const CODE_LENGTH = 6;
const QR_SIZE = 168;
const emptyCode = (): string[] => Array.from({ length: CODE_LENGTH }, () => '');

const PRIMARY_BUTTON =
  'rounded-lg bg-accent px-3 py-2 text-sm font-medium text-accent-contrast hover:bg-accent-hover disabled:opacity-60';
const SECONDARY_BUTTON =
  'rounded-lg border border-app bg-app px-3 py-2 text-sm font-medium text-app hover:bg-surface-raised disabled:opacity-60';

interface TwoFactorSectionProps {
  enabled: boolean;
  onChanged: () => void;
}

/** Turning two-factor codes on and off for the signed-in account. */
export function TwoFactorSection({ enabled, onChanged }: TwoFactorSectionProps): ReactNode {
  const { t } = useTranslation();
  const [enrollment, setEnrollment] = useState<{ secret: string; uri: string } | null>(null);
  const [code, setCode] = useState<string[]>(emptyCode);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = (action: () => Promise<void>): void => {
    setBusy(true);
    setError(null);
    action()
      .catch(() => {
        setError(t('settings.error.generic'));
      })
      .finally(() => {
        setBusy(false);
      });
  };

  const begin = (): void => {
    run(async () => {
      const started = await startTotpEnrollment();
      setEnrollment({ secret: started.secret, uri: started.provisioningUri });
      setCode(emptyCode());
    });
  };

  const confirm = (event: SyntheticEvent<HTMLFormElement>): void => {
    event.preventDefault();
    run(async () => {
      try {
        await confirmTotpEnrollment(code.join(''));
      } catch (cause) {
        setError(t('settings.twoFactor.badCode'));
        throw cause;
      }
      setEnrollment(null);
      onChanged();
    });
  };

  const turnOff = (): void => {
    run(async () => {
      await disableTotp();
      onChanged();
    });
  };

  return (
    <section aria-labelledby="two-factor-heading" className="space-y-4">
      <div>
        <h2
          id="two-factor-heading"
          className="text-sm font-semibold uppercase tracking-wider text-muted"
        >
          {t('settings.twoFactor.heading')}
        </h2>
        <p className="mt-1 text-sm text-muted">{t('settings.twoFactor.description')}</p>
      </div>

      {error !== null && <ErrorBanner message={error} />}

      <div className="rounded-xl border border-app bg-surface p-4 shadow-app-sm">
        <p className="flex items-center gap-2 text-sm text-app">
          {enabled ? (
            <ShieldCheck className="h-4 w-4 text-success" aria-hidden="true" />
          ) : (
            <ShieldOff className="h-4 w-4 text-muted" aria-hidden="true" />
          )}
          {enabled ? t('settings.twoFactor.on') : t('settings.twoFactor.off')}
        </p>

        {enabled && (
          <button
            type="button"
            onClick={turnOff}
            disabled={busy}
            className={`mt-4 ${SECONDARY_BUTTON}`}
          >
            {t('settings.twoFactor.turnOff')}
          </button>
        )}

        {!enabled && enrollment === null && (
          <button
            type="button"
            onClick={begin}
            disabled={busy}
            className={`mt-4 ${PRIMARY_BUTTON}`}
          >
            {t('settings.twoFactor.turnOn')}
          </button>
        )}

        {!enabled && enrollment !== null && (
          <form className="mt-4 space-y-4" onSubmit={confirm}>
            <p className="text-sm text-muted">{t('settings.twoFactor.scan')}</p>
            <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center">
              <div className="rounded-lg bg-white p-3">
                <QRCodeSVG value={enrollment.uri} size={QR_SIZE} />
              </div>
              <div className="min-w-0">
                <p className="text-xs text-muted">{t('settings.twoFactor.secret')}</p>
                <code className="block break-all font-mono text-sm text-app">
                  {enrollment.secret}
                </code>
              </div>
            </div>

            <OtpInput
              value={code}
              onChange={setCode}
              label={t('login.codeLabel')}
              digitLabel={(position) =>
                t('login.codeDigitLabel', { index: position, total: CODE_LENGTH })
              }
            />

            <div className="flex gap-3">
              <button type="submit" disabled={busy} className={PRIMARY_BUTTON}>
                {t('settings.twoFactor.confirm')}
              </button>
              <button
                type="button"
                onClick={() => {
                  setEnrollment(null);
                }}
                disabled={busy}
                className={SECONDARY_BUTTON}
              >
                {t('settings.cancel')}
              </button>
            </div>
          </form>
        )}
      </div>
    </section>
  );
}
