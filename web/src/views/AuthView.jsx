import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Hourglass } from 'lucide-react';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';

const AuthView = ({ loginGuest, loginDiscord }) => {
  const { t } = useTranslation();
  const [guestName, setGuestName] = useState('');
  const [discordId, setDiscordId] = useState('');

  return (
    <div className="flex h-screen bg-fantasy-dark items-center justify-center p-4 relative">
      <div className="absolute top-4 right-4">
        <LanguageSwitcher />
      </div>
      <div className="max-w-md w-full bg-fantasy-panel border border-fantasy-border p-8 rounded shadow-2xl">
        <div className="flex flex-col items-center mb-8">
          <Hourglass size={48} className="text-fantasy-accent mb-4 animate-pulse" />
          <h1 className="font-rpg text-3xl font-bold text-gray-100 tracking-wider">{t('auth.title', 'Hikayat')}</h1>
          <p className="text-sm text-gray-400 mt-2">{t('auth.tagline', 'AI RPG Console')}</p>
        </div>

        <div className="space-y-6">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = guestName.trim();
              if (trimmed) loginGuest(trimmed);
            }}
            className="bg-black/20 p-4 rounded border border-fantasy-border/50"
          >
            <h2 className="text-sm uppercase tracking-widest text-gray-400 mb-3">{t('auth.guest_access', 'Guest Access')}</h2>
            <input 
              type="text" 
              placeholder={t('auth.enter_name_placeholder', 'Enter your name...')} 
              className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-gray-200 focus:border-fantasy-accent outline-none transition-colors mb-3"
              value={guestName}
              onChange={(e) => setGuestName(e.target.value)}
            />
            <button 
              type="submit"
              disabled={!guestName.trim()}
              className="w-full bg-fantasy-accent/10 hover:bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/50 p-2 rounded transition-colors disabled:opacity-40"
            >
              {t('auth.enter_forge', 'Enter the Forge')}
            </button>
          </form>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              const trimmed = discordId.trim();
              if (trimmed) loginDiscord(trimmed);
            }}
            className="bg-black/20 p-4 rounded border border-fantasy-border/50"
          >
            <h2 className="text-sm uppercase tracking-widest text-gray-400 mb-3">{t('auth.discord_link', 'Discord Link')}</h2>
            <input 
              type="text" 
              placeholder={t('auth.discord_placeholder', 'Discord ID or Username...')} 
              className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-gray-200 focus:border-fantasy-accent outline-none transition-colors mb-3"
              value={discordId}
              onChange={(e) => setDiscordId(e.target.value)}
            />
            <button 
              type="submit"
              disabled={!discordId.trim()}
              className="w-full bg-[#5865F2]/10 hover:bg-[#5865F2]/20 text-[#5865F2] border border-[#5865F2]/50 p-2 rounded transition-colors disabled:opacity-40"
            >
              {t('auth.connect_discord', 'Connect Discord')}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
};

export default AuthView;
