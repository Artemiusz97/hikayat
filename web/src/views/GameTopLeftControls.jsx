import { Compass, Map, MapPin, WifiOff } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { MotionButton } from '../components/Common/MotionPrimitives';
import {
  formatClockTime,
  getDayOfWeekLabel,
  getTimeOfDayPhaseInfo,
} from '../utils/timeFormat';

const GameTopLeftControls = ({
  compact = false,
  session,
  leftPanel,
  clockFormat,
  wsStatus = 'idle',
  processingTurn = false,
  inCombat = false,
  hasUtilityAlert = false,
  onToggleUtility,
  onToggleWorldMap,
  onOpenTimeSkip,
}) => {
  const { t } = useTranslation();

  const locationLabel = (() => {
    const raw = session?.current_location || '';
    const parts = String(raw)
      .split(/\s*(?:->|→|➔|>|›|»|\|)\s*/)
      .filter(Boolean);
    return parts[parts.length - 1] || session?.scene_title || 'Hikayat';
  })();

  const currentDay = Number(session?.current_day || 1);
  const currentMinute =
    session?.current_minute !== undefined && session?.current_minute !== null
      ? Number(session.current_minute)
      : 480;
  const turnCount = Number.isFinite(Number(session?.turn_count))
    ? Math.max(0, Math.floor(Number(session.turn_count)))
    : Array.isArray(session?.history)
      ? session.history.filter(
          (entry) => entry && typeof entry === 'object' && entry.type !== 'scene'
        ).length
      : 0;

  const dayLabel = getDayOfWeekLabel(currentDay, t);
  const shortDayLabel = getDayOfWeekLabel(currentDay, t, { short: true });
  const formattedClock = formatClockTime(currentMinute, clockFormat);
  const timePhase = getTimeOfDayPhaseInfo(currentMinute, t);
  const TimePhaseIcon = timePhase.Icon;
  const turnLabel = t('scene.turn_counter', {
    count: turnCount,
    defaultValue: `Turn ${turnCount}`,
  });
  const shortTurnLabel = t('scene.turn_counter_short', {
    count: turnCount,
    defaultValue: `T${turnCount}`,
  });
  const dayCountLabel = t('scene.day_counter', {
    count: currentDay,
    defaultValue: `Day ${currentDay}`,
  });
  const shortDayCountLabel = t('scene.day_counter_short', {
    count: currentDay,
    defaultValue: `D${currentDay}`,
  });

  return (
    <div
      className={
        compact
          ? 'flex items-center gap-1.5 min-w-0 flex-1'
          : 'flex flex-wrap items-center gap-1.5 min-w-0'
      }
    >
      <MotionButton
        onClick={onToggleUtility}
        aria-expanded={leftPanel === 'utility'}
        aria-label={t('nav.utility', 'Utilities')}
        title={t('nav.utility', 'Utilities')}
        className={`hk-acrylic-pill w-10 h-10 grid place-items-center shrink-0 relative ${
          leftPanel === 'utility'
            ? 'text-fantasy-accent ring-1 ring-fantasy-accent/60'
            : 'text-gray-100 hover:text-fantasy-accent'
        }`}
      >
        <Compass size={18} />
        {hasUtilityAlert && (
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-fantasy-accent animate-pulse" />
        )}
      </MotionButton>

      <MotionButton
        onClick={onToggleWorldMap}
        aria-expanded={leftPanel === 'map'}
        aria-label={t('nav.map', 'World Map')}
        title={t('nav.map', 'World Map')}
        className={`hk-acrylic-pill w-10 h-10 grid place-items-center shrink-0 ${
          leftPanel === 'map'
            ? 'text-fantasy-accent ring-1 ring-fantasy-accent/60'
            : 'text-gray-100 hover:text-fantasy-accent'
        }`}
      >
        <Map size={18} />
      </MotionButton>

      <MotionButton
        onClick={onToggleWorldMap}
        title={session?.current_location || locationLabel}
        className={`hk-acrylic-pill min-h-10 h-auto py-1.5 px-3.5 inline-flex items-center gap-2 text-left min-w-0 ${
          compact ? 'flex-1' : 'max-w-[clamp(10rem,13vw,22rem)]'
        }`}
      >
        <MapPin size={14} className="text-fantasy-accent shrink-0" />
        <span className="text-xs font-semibold text-gray-100 truncate">
          {locationLabel}
        </span>
      </MotionButton>

      <MotionButton
        onClick={onOpenTimeSkip}
        disabled={processingTurn || inCombat}
        title={
          inCombat
            ? `${dayLabel} • ${formattedClock} (${timePhase.label}) • ${dayCountLabel} • ${turnLabel} — ${t('actions.cannot_rest_combat', 'Cannot rest during combat')}`
            : `${dayLabel} • ${formattedClock} (${timePhase.label}) • ${dayCountLabel} • ${turnLabel} — ${t('actions.open_chronos', 'Open Chronos Dial to advance time and rest')}`
        }
        className={`hk-acrylic-pill min-h-10 h-auto py-1.5 ${
          compact ? 'px-2.5' : 'px-3.5'
        } inline-flex items-center gap-1.5 shrink-0 disabled:opacity-75`}
      >
        <TimePhaseIcon
          size={14}
          className={`${timePhase.colorClass} shrink-0`}
          aria-hidden="true"
        />
        <span
          className={`${
            compact ? 'text-[11px]' : 'text-xs'
          } font-semibold text-gray-100 tabular-nums whitespace-nowrap`}
        >
          {compact
            ? `${shortDayLabel} • ${formattedClock} • ${shortDayCountLabel} • ${shortTurnLabel}`
            : `${dayLabel} • ${formattedClock} • ${dayCountLabel} • ${turnLabel}`}
        </span>
      </MotionButton>

      {wsStatus === 'reconnecting' && (
        <span
          role="status"
          aria-live="polite"
          className="hk-acrylic-pill h-10 px-3 inline-flex items-center gap-1.5 shrink-0 text-xs font-semibold text-amber-300 border border-amber-500/40 bg-amber-950/50"
        >
          <WifiOff size={13} className="animate-pulse shrink-0" />
          <span className={compact ? 'hidden sm:inline' : ''}>
            {t('status.reconnecting', 'Reconnecting…')}
          </span>
        </span>
      )}
    </div>
  );
};

export default GameTopLeftControls;
