import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Hourglass, ArrowRight } from 'lucide-react';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
import ThemeSwitcher from '../components/Common/ThemeSwitcher';

const AuthView = ({ loginGuest, loginDiscord }) => {
  const { t } = useTranslation();
  const [mode, setMode] = useState('guest'); // 'guest' | 'discord'
  const [guestName, setGuestName] = useState('');
  const [discordId, setDiscordId] = useState('');

  const isGuest = mode === 'guest';
  const value = isGuest ? guestName : discordId;

  const submit = (e) => {
    e.preventDefault();
    const trimmed = value.trim();
    if (!trimmed) return;
    if (isGuest) loginGuest(trimmed);
    else loginDiscord(trimmed);
  };

  return (
    <div className="flex h-full items-center justify-center p-4 relative">
      <div className="absolute top-3 right-3 flex items-center gap-1">
        <ThemeSwitcher />
        <LanguageSwitcher />
      </div>

      <div className="w-full max-w-sm hk-enter">
        <div className="flex flex-col items-center text-center mb-8">
          <div className="grid place-items-center w-16 h-16 rounded-2xl bg-fantasy-accent text-black shadow-lg mb-5">
            <Hourglass size={30} />
          </div>
          <h1 className="hk-display text-4xl font-bold text-gray-50">{t('auth.title', 'Hikayat')}</h1>
          <p className="text-sm text-gray-400 mt-2">{t('auth.tagline', 'AI RPG Console')}</p>
        </div>

        <div className="hk-surface p-5 sm:p-6">
          <div className="hk-segmented mb-5" role="tablist">
            <button type="button" role="tab" aria-selected={isGuest} onClick={() => setMode('guest')}>
              {t('auth.guest_access', 'Guest Access')}
            </button>
            <button type="button" role="tab" aria-selected={!isGuest} onClick={() => setMode('discord')}>
              {t('auth.discord_link', 'Discord Link')}
            </button>
          </div>

          <form onSubmit={submit} className="space-y-3" key={mode}>
            <input
              type="text"
              autoFocus
              autoComplete={isGuest ? 'nickname' : 'username'}
              placeholder={isGuest ? t('auth.enter_name_placeholder', 'Enter your name...') : t('auth.discord_placeholder', 'Discord ID or Username...')}
              className="hk-input h-11 animate-fadeIn"
              value={value}
              onChange={(e) => (isGuest ? setGuestName(e.target.value) : setDiscordId(e.target.value))}
            />
            <button
              type="submit"
              disabled={!value.trim()}
              className={`hk-btn w-full h-11 ${isGuest ? 'hk-btn-primary' : 'text-white'}`}
              style={isGuest ? undefined : { background: '#5865F2', color: '#fff' }}
            >
              {isGuest ? t('auth.enter_forge', 'Enter the Forge') : t('auth.connect_discord', 'Connect Discord')}
              <ArrowRight size={16} />
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AuthView;
