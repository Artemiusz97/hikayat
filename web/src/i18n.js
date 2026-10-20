import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

import en from './locales/en.json';
import pl from './locales/pl.json';
import ms from './locales/ms.json';
import zh from './locales/zh.json';
import de from './locales/de.json';

export const AVAILABLE_LANGUAGES = [
  { code: 'en', label: 'English', flag: '🇬🇧', short: 'EN' },
  { code: 'pl', label: 'Polski', flag: '🇵🇱', short: 'PL' },
  { code: 'ms', label: 'Melayu', flag: '🇲🇾', short: 'MS' },
  { code: 'zh', label: '中文', flag: '🇨🇳', short: 'ZH' },
  { code: 'de', label: 'Deutsch', flag: '🇩🇪', short: 'DE' }
];

if (typeof window !== 'undefined' && !localStorage.getItem('hikayat_ui_language') && localStorage.getItem('hikayat_language')) {
  localStorage.setItem('hikayat_ui_language', localStorage.getItem('hikayat_language'));
}

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      en: { translation: en },
      pl: { translation: pl },
      ms: { translation: ms },
      zh: { translation: zh },
      de: { translation: de }
    },
    fallbackLng: 'en',
    supportedLngs: ['en', 'pl', 'ms', 'zh', 'de'],
    detection: {
      order: ['localStorage', 'navigator'],
      caches: ['localStorage'],
      lookupLocalStorage: 'hikayat_ui_language'
    },
    interpolation: {
      escapeValue: false
    }
  });

export default i18n;
