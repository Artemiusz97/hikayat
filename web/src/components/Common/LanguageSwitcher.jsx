import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Globe, ChevronDown, Check, Monitor, Sparkles } from 'lucide-react';
import { AVAILABLE_LANGUAGES } from '../../i18n';

export const LanguageSwitcher = ({ settingsHook, className = '' }) => {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const [activeTab, setActiveTab] = useState('ui'); // 'ui' | 'narration'
  const containerRef = useRef(null);

  const currentUiLang = (i18n.language || 'en').split('-')[0].toLowerCase();
  const currentNarrLang = (settingsHook?.settings?.narration_language || settingsHook?.settings?.language || 'en').split('-')[0].toLowerCase();

  const activeUiOption = AVAILABLE_LANGUAGES.find(l => l.code === currentUiLang) || AVAILABLE_LANGUAGES[0];
  const activeNarrOption = AVAILABLE_LANGUAGES.find(l => l.code === currentNarrLang) || AVAILABLE_LANGUAGES[0];

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectUi = (code) => {
    i18n.changeLanguage(code);
    localStorage.setItem('hikayat_ui_language', code);
    localStorage.setItem('hikayat_language', code);
    if (settingsHook?.updateSettings) {
      settingsHook.updateSettings({ ui_language: code }).catch(() => {});
    }
    setOpen(false);
  };

  const handleSelectNarr = (code) => {
    if (settingsHook?.updateSettings) {
      settingsHook.updateSettings({ narration_language: code, language: code }).catch(() => {});
    }
    setOpen(false);
  };

  const pillLabel = activeUiOption.short === activeNarrOption.short
    ? activeUiOption.short
    : `${activeUiOption.short} / ${activeNarrOption.short}`;

  return (
    <div className={`relative inline-block text-left ${className}`} ref={containerRef}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 px-2 py-1 bg-black/60 hover:bg-neutral-900 border border-neutral-700 hover:border-fantasy-accent/60 rounded-lg text-xs font-medium text-gray-200 transition-all shadow-sm focus:outline-none"
        title="Language Settings"
      >
        <Globe size={13} className="text-fantasy-accent" />
        <span className="font-mono text-[11px] font-bold tracking-wider">{pillLabel}</span>
        <ChevronDown size={11} className={`text-gray-400 transition-transform duration-200 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 mt-1.5 w-48 rounded-lg bg-neutral-950 border border-neutral-800 shadow-xl z-50 overflow-hidden backdrop-blur-md animate-in fade-in zoom-in-95 duration-100">
          {/* Dual Toggle Tabs */}
          <div className="flex border-b border-neutral-800/80 bg-black/50 p-1 gap-1">
            <button
              type="button"
              onClick={() => setActiveTab('ui')}
              className={`flex-1 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1 ${
                activeTab === 'ui'
                  ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 font-bold'
                  : 'text-gray-400 hover:text-gray-200 border border-transparent'
              }`}
            >
              <Monitor size={11} />
              <span>{t('settings.ui_tab', 'UI')}</span>
              <span className="font-mono text-[9px] opacity-75">({activeUiOption.short})</span>
            </button>
            <button
              type="button"
              onClick={() => setActiveTab('narration')}
              className={`flex-1 py-1 rounded text-[10px] font-bold uppercase tracking-wider transition-all flex items-center justify-center gap-1 ${
                activeTab === 'narration'
                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/40 font-bold'
                  : 'text-gray-400 hover:text-gray-200 border border-transparent'
              }`}
            >
              <Sparkles size={11} />
              <span>{t('settings.narration_tab', 'Story')}</span>
              <span className="font-mono text-[9px] opacity-75">({activeNarrOption.short})</span>
            </button>
          </div>

          {/* Section Header (dynamically translated) */}
          <div className="px-2.5 py-1 text-[10px] font-semibold text-gray-400 border-b border-neutral-800/80 uppercase tracking-wider flex items-center justify-between">
            <span>
              {activeTab === 'ui'
                ? t('settings.ui_language_short', 'UI Language')
                : t('settings.narration_language_short', 'Story Language')}
            </span>
            <span className="font-mono text-[9px] text-fantasy-accent">
              {activeTab === 'ui' ? activeUiOption.short : activeNarrOption.short}
            </span>
          </div>

          {/* Options */}
          <div className="py-1">
            {AVAILABLE_LANGUAGES.map((lang) => {
              const isSelected = activeTab === 'ui'
                ? lang.code === currentUiLang
                : lang.code === currentNarrLang;

              return (
                <button
                  key={lang.code}
                  type="button"
                  onClick={() => activeTab === 'ui' ? handleSelectUi(lang.code) : handleSelectNarr(lang.code)}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 text-xs text-left transition-colors ${
                    isSelected
                      ? activeTab === 'ui'
                        ? 'bg-fantasy-accent/15 text-fantasy-accent font-semibold'
                        : 'bg-amber-500/15 text-amber-300 font-semibold'
                      : 'text-gray-300 hover:bg-neutral-900 hover:text-white'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <span className="text-sm">{lang.flag}</span>
                    <span>{lang.label}</span>
                  </div>
                  {isSelected && <Check size={12} className={activeTab === 'ui' ? "text-fantasy-accent" : "text-amber-400"} />}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default LanguageSwitcher;
