import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { ArrowRight, Loader2 } from 'lucide-react';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
import ThemeSwitcher from '../components/Common/ThemeSwitcher';
import AcrylicModeSwitcher from '../components/Common/AcrylicModeSwitcher';
import HikayatLogoIcon from '../components/Common/HikayatLogoIcon';
import { AcrylicPanel, MotionButton } from '../components/Common/MotionPrimitives';

const AuthView = ({ loginGuest, loginDiscord }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState('guest'); // 'guest' | 'discord'
  const [guestName, setGuestName] = useState('');
  const [discordId, setDiscordId] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const isGuest = mode === 'guest';
  const value = isGuest ? guestName : discordId;

  const submit = async (e) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed || submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await (isGuest ? loginGuest(trimmed) : loginDiscord(trimmed));
    } catch (err) {
      setError(
        err?.message || t('auth.login_failed', 'Could not sign in. Please try again.')
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="h-full w-full overflow-y-auto overflow-x-clip custom-scrollbar relative flex flex-col items-center px-4 py-16">
      <div className="fixed top-3 right-3 z-20 hk-acrylic-pill px-1.5 py-1 flex items-center gap-0.5 max-w-[calc(100dvw-1.5rem)]">
        <ThemeSwitcher compact />
        <AcrylicModeSwitcher />
        <LanguageSwitcher />
      </div>

      <div className="my-auto w-full max-w-sm flex flex-col items-center gap-4 min-w-0">
        <AcrylicPanel
          variant="panel"
          origin="top"
          className="w-full px-6 py-5 flex flex-col items-center text-center"
        >
          <div className="grid place-items-center w-14 h-14 rounded-full bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/35 mb-3">
            <HikayatLogoIcon size={28} />
          </div>
          <h1 className="hk-display text-3xl sm:text-4xl font-bold text-gray-50">
            {t('auth.title', 'Hikayat')}
          </h1>
          <p className="text-xs sm:text-sm text-gray-300 mt-1.5 text-balance">
            {t('auth.tagline', 'Living Chronicles · Interactive RPG')}
          </p>
        </AcrylicPanel>

        <AcrylicPanel
          variant="panel"
          origin="bottom"
          className="w-full p-5 sm:p-6"
        >
          <div
            className="flex border-b border-fantasy-border/40 mb-5"
            role="tablist"
          >
            <button
              type="button"
              role="tab"
              aria-selected={isGuest}
              onClick={() => {
                setMode('guest');
                setError(null);
              }}
              className={`flex-1 pb-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-colors truncate ${
                isGuest
                  ? 'border-fantasy-accent text-fantasy-accent'
                  : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              {t('auth.guest_access', 'Guest Access')}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={!isGuest}
              onClick={() => {
                setMode('discord');
                setError(null);
              }}
              className={`flex-1 pb-2.5 text-xs sm:text-sm font-semibold border-b-2 transition-colors truncate ${
                !isGuest
                  ? 'border-fantasy-accent text-fantasy-accent'
                  : 'border-transparent text-gray-400 hover:text-gray-200'
              }`}
            >
              {t('auth.discord_link', 'Discord Link')}
            </button>
          </div>

          <form onSubmit={submit} className="space-y-3" key={mode}>
            <input
              type="text"
              autoFocus
              disabled={submitting}
              autoComplete={isGuest ? 'nickname' : 'username'}
              aria-label={
                isGuest
                  ? t('auth.guest_access', 'Guest Access')
                  : t('auth.discord_link', 'Discord Link')
              }
              placeholder={
                isGuest
                  ? t('auth.enter_name_placeholder', 'Enter your name...')
                  : t('auth.discord_placeholder', 'Discord ID or Username...')
              }
              className="hk-input h-11 animate-fadeIn disabled:opacity-60"
              value={value}
              onChange={(e) => {
                if (error) setError(null);
                if (isGuest) setGuestName(e.target.value);
                else setDiscordId(e.target.value);
              }}
            />
            {error && (
              <div
                role="alert"
                className="px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-200 text-xs"
              >
                {error}
              </div>
            )}
            <MotionButton
              type="submit"
              disabled={!value.trim() || submitting}
              className={`hk-btn w-full h-11 disabled:opacity-50 ${isGuest ? 'hk-btn-primary' : 'text-white'}`}
              style={isGuest ? undefined : { background: '#5865F2', color: '#fff' }}
            >
              <span>
                {submitting
                  ? t('common.loading', 'Loading...')
                  : isGuest
                    ? t('auth.enter_forge', 'Enter the Forge')
                    : t('auth.connect_discord', 'Connect Discord')}
              </span>
              {submitting ? (
                <Loader2 size={16} className="animate-spin" />
              ) : (
                <ArrowRight size={16} />
              )}
            </MotionButton>
          </form>
        </AcrylicPanel>
      </div>
    </div>
  );
};

export default AuthView;
