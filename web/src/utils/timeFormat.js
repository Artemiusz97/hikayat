import {
  CloudSun,
  Moon,
  MoonStar,
  Sun,
  SunMedium,
  Sunrise,
  Sunset,
} from 'lucide-react';

export const DAYS_OF_WEEK_KEYS = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
];

export const DEFAULT_DAY_NAMES = {
  monday: 'Monday',
  tuesday: 'Tuesday',
  wednesday: 'Wednesday',
  thursday: 'Thursday',
  friday: 'Friday',
  saturday: 'Saturday',
  sunday: 'Sunday',
};

export const DEFAULT_DAY_SHORT_NAMES = {
  monday: 'Mon',
  tuesday: 'Tue',
  wednesday: 'Wed',
  thursday: 'Thu',
  friday: 'Fri',
  saturday: 'Sat',
  sunday: 'Sun',
};

export const normalizeMinute = (totalMinutes) => {
  const num = Number(totalMinutes);
  const safe = Number.isFinite(num) ? Math.floor(num) : 480;
  return ((safe % 1440) + 1440) % 1440;
};

export const getDayOfWeekIndex = (currentDay) => {
  const num = Number(currentDay);
  const safeDay = Number.isFinite(num) && num >= 1 ? Math.floor(num) : 1;
  return (safeDay - 1) % 7;
};

export const getDayOfWeekKey = (currentDay) =>
  DAYS_OF_WEEK_KEYS[getDayOfWeekIndex(currentDay)];

export const isWeekendDay = (currentDay) => {
  const idx = getDayOfWeekIndex(currentDay);
  return idx === 5 || idx === 6;
};

export const getDayOfWeekLabel = (currentDay, t = null, { short = false } = {}) => {
  const key = getDayOfWeekKey(currentDay);
  const fallback = short ? DEFAULT_DAY_SHORT_NAMES[key] : DEFAULT_DAY_NAMES[key];
  if (typeof t === 'function') {
    const scope = short ? 'time.days_short' : 'time.days';
    return t(`${scope}.${key}`, fallback);
  }
  return fallback;
};

export const formatClockTime = (totalMinutes, clockFormat = '24h') => {
  const norm = normalizeMinute(totalMinutes);
  const hours = Math.floor(norm / 60);
  const mins = norm % 60;
  const mm = String(mins).padStart(2, '0');
  if (clockFormat === '12h') {
    const period = hours >= 12 ? 'PM' : 'AM';
    const h12 = hours % 12 === 0 ? 12 : hours % 12;
    return `${h12}:${mm} ${period}`;
  }
  return `${String(hours).padStart(2, '0')}:${mm}`;
};

export const getTimeOfDayPhaseInfo = (totalMinutes, t = null) => {
  const norm = normalizeMinute(totalMinutes);
  const tr = (k, def) => (typeof t === 'function' ? t(k, def) : def);

  if (norm < 300) {
    return {
      key: 'midnight',
      label: tr('timeskip.phase_midnight', 'Midnight'),
      Icon: MoonStar,
      colorClass: 'text-indigo-300',
      emoji: '🌌',
    };
  }
  if (norm < 420) {
    return {
      key: 'dawn',
      label: tr('timeskip.phase_dawn', 'Dawn'),
      Icon: Sunrise,
      colorClass: 'text-amber-300',
      emoji: '🌅',
    };
  }
  if (norm < 660) {
    return {
      key: 'morning',
      label: tr('timeskip.phase_morning', 'Morning'),
      Icon: CloudSun,
      colorClass: 'text-yellow-300',
      emoji: '🌤️',
    };
  }
  if (norm < 840) {
    return {
      key: 'noon',
      label: tr('timeskip.phase_noon', 'Noon'),
      Icon: Sun,
      colorClass: 'text-amber-400',
      emoji: '☀️',
    };
  }
  if (norm < 1020) {
    return {
      key: 'afternoon',
      label: tr('timeskip.phase_afternoon', 'Afternoon'),
      Icon: SunMedium,
      colorClass: 'text-amber-200',
      emoji: '☀️',
    };
  }
  if (norm < 1200) {
    return {
      key: 'dusk',
      label: tr('timeskip.phase_dusk', 'Dusk'),
      Icon: Sunset,
      colorClass: 'text-orange-400',
      emoji: '🌇',
    };
  }
  return {
    key: 'night',
    label: tr('timeskip.phase_night', 'Night'),
    Icon: Moon,
    colorClass: 'text-indigo-300',
    emoji: '🌙',
  };
};

export const formatSaveDate = (ts) => {
  if (!ts) return '';
  return new Date(ts * 1000).toLocaleString([], {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
};
