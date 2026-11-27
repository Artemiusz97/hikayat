import { useState, useMemo, useEffect, useId } from 'react';
import { useTranslation } from 'react-i18next';
import {
  AlertTriangle,
  ArrowRight,
  BedDouble,
  Clock,
  Hourglass,
  Minus,
  Moon,
  Plus,
  Sofa,
  Sun,
  Sunrise,
  Sunset,
  Tent,
  Users,
  X,
} from 'lucide-react';
import { AcrylicModal, MotionButton } from '../Common/MotionPrimitives';
import AnalogClockDial from './AnalogClockDial';
import { useUiPreferences } from '../../theme/UiPreferencesProvider';
import {
  formatClockTime,
  getDayOfWeekLabel,
  getTimeOfDayPhaseInfo,
  normalizeMinute,
} from '../../utils/timeFormat';

const MIN_SKIP_MINUTES = 15;
const MAX_SKIP_MINUTES = 1440;
const STEP_MINUTES = 15;

const clampSkipMinutes = (mins) =>
  Math.max(MIN_SKIP_MINUTES, Math.min(MAX_SKIP_MINUTES, Math.round(Number(mins) || MIN_SKIP_MINUTES)));

const formatCompactDuration = (minutes) => {
  const safe = clampSkipMinutes(minutes);
  const h = Math.floor(safe / 60);
  const m = safe % 60;
  if (h <= 0) return `${m}m`;
  if (m === 0) return `${h}h`;
  return `${h}h ${m}m`;
};

const computeDiffToClockMinute = (curMin, targetClockMin) => {
  const normCur = normalizeMinute(curMin);
  const diff = (targetClockMin - normCur + 1440) % 1440;
  return clampSkipMinutes(diff < MIN_SKIP_MINUTES ? diff + 1440 : diff);
};

const TimeSkipModal = ({
  isOpen,
  onClose,
  session,
  phoneHook,
  onAction,
  processing,
}) => {
  const { t } = useTranslation();
  const { clockFormat, timeSkipControl } = useUiPreferences();
  const useAnalogDial = timeSkipControl === 'dial';
  const sliderId = useId();

  const currentDay = Number(session?.current_day || 1);
  const currentMinute = Number(
    session?.current_minute !== undefined && session?.current_minute !== null
      ? session.current_minute
      : 480
  );
  const rawTimeScale = session?.realm_hud?.time_scale;
  const parsedTimeScale =
    rawTimeScale !== undefined && rawTimeScale !== null ? Number(rawTimeScale) : 1;
  const timeScale = Number.isFinite(parsedTimeScale) ? Math.max(0, parsedTimeScale) : 1;
  const isTemporalStasis = timeScale <= 0;
  const isScaledTime = !isTemporalStasis && Math.abs(timeScale - 1) > 0.001;

  const sleepContext = useMemo(
    () =>
      session?.sleep_context || {
        surface: 'camp',
        can_sleep: true,
        recovery_ratio: 1.0,
        surface_label: 'Camp',
        reason: 'Resting available.',
      },
    [session?.sleep_context]
  );

  const canSleep = Boolean(sleepContext.can_sleep);
  const surface = sleepContext.surface || (canSleep ? 'bed' : 'none');
  const recoveryRatio =
    sleepContext.recovery_ratio !== undefined
      ? Number(sleepContext.recovery_ratio)
      : canSleep
        ? 1.0
        : 0.0;

  const [skipMinutes, setSkipMinutes] = useState(120);
  const [mode, setMode] = useState(() => (canSleep ? 'rest' : 'wait'));

  useEffect(() => {
    setMode((prev) => {
      if (!canSleep) return 'wait';
      return isOpen ? 'rest' : prev;
    });
  }, [canSleep, isOpen]);

  const effectiveAction = useMemo(() => {
    if (!canSleep || mode !== 'rest') return 'wait';
    if (skipMinutes >= 360) return 'sleep';
    if (skipMinutes >= 30) return 'nap';
    return 'wait';
  }, [canSleep, mode, skipMinutes]);

  const isWaitBlockedByStasis = isTemporalStasis && effectiveAction === 'wait';
  const mortalElapsedMinutes = isTemporalStasis
    ? 0
    : Math.round(skipMinutes * timeScale);

  const recoveryPreview = useMemo(() => {
    if (isWaitBlockedByStasis) {
      return {
        hpPercent: 0,
        hint: t(
          'timeskip.wait_stasis_blocked',
          'Waiting cannot advance outside time during Temporal Stasis.'
        ),
      };
    }
    if (!canSleep || mode !== 'rest') {
      return {
        hpPercent: 0,
        hint: t('timeskip.wait_only_hint', 'Time passes only · No recovery'),
      };
    }
    if (skipMinutes < 30) {
      return {
        hpPercent: 0,
        hint: t('timeskip.rest_too_short_hint', 'Needs 30m+ to rest · Passes time only'),
      };
    }
    if (skipMinutes >= 360) {
      const pct = Math.round(recoveryRatio * 100);
      return {
        hpPercent: pct,
        hint: t('timeskip.rest_full_hint', {
          pct,
          defaultValue: 'Full rest · {{pct}}% HP/MP · Clears fatigue',
        }),
      };
    }
    const napFraction = Math.min(1.0, skipMinutes / 480);
    const pct = Math.round(napFraction * recoveryRatio * 100);
    return {
      hpPercent: pct,
      hint: t('timeskip.rest_nap_hint', {
        pct,
        defaultValue: 'Nap · +{{pct}}% HP/MP',
      }),
    };
  }, [isWaitBlockedByStasis, canSleep, mode, skipMinutes, recoveryRatio, t]);

  const targetMinute = currentMinute + mortalElapsedMinutes;
  const currentNormMinute = normalizeMinute(currentMinute);
  const targetNormMinute = normalizeMinute(targetMinute);
  const targetDayOffset = Math.floor((currentNormMinute + mortalElapsedMinutes) / 1440);
  const targetDay = currentDay + targetDayOffset;

  const currentTimeStr = formatClockTime(currentMinute, clockFormat);
  const targetTimeStr = formatClockTime(targetMinute, clockFormat);
  const targetTimePromptStr = formatClockTime(targetMinute, '24h');
  const currentDayLabel = getDayOfWeekLabel(currentDay, t);
  const targetDayLabel = getDayOfWeekLabel(targetDay, t);
  const currentPhase = getTimeOfDayPhaseInfo(currentMinute, t);
  const targetPhase = getTimeOfDayPhaseInfo(targetMinute, t);
  const CurrentPhaseIcon = currentPhase.Icon;
  const TargetPhaseIcon = targetPhase.Icon;
  const compactDuration = formatCompactDuration(skipMinutes);

  const currentDayPct = (currentNormMinute / 1440) * 100;
  const targetDayPct = (targetNormMinute / 1440) * 100;

  const SurfaceIcon =
    surface === 'couch' ? Sofa : surface === 'camp' ? Tent : BedDouble;
  const surfaceLabel =
    sleepContext.surface_label || (canSleep ? 'Bed' : 'None');

  const isMultiplayer = Boolean(
    session?.party_members && session.party_members.length > 1
  );

  // Upcoming commitments & appointments from phoneHook
  const rawCommitments =
    Array.isArray(phoneHook?.commitments) && phoneHook.commitments.length > 0
      ? phoneHook.commitments
      : phoneHook?.appointments || [];
  const currentAbsMinute = (currentDay - 1) * 1440 + currentNormMinute;
  const targetAbsMinute = currentAbsMinute + mortalElapsedMinutes;

  const upcomingCommitments = rawCommitments
    .map((apt) => {
      if (!apt || typeof apt !== 'object') return null;
      const statusLow = String(apt.status || 'pending').trim().toLowerCase();
      if (['cancelled', 'canceled', 'completed', 'expired', 'missed'].includes(statusLow)) {
        return null;
      }
      let absMin = null;
      if (
        apt.start_minute !== undefined &&
        apt.start_minute !== null &&
        Number.isFinite(Number(apt.start_minute))
      ) {
        const schedDay = Math.max(1, Number(apt.scheduled_day || currentDay) || currentDay);
        absMin = (schedDay - 1) * 1440 + normalizeMinute(apt.start_minute);
      } else if (
        apt.target_minute !== undefined &&
        apt.target_minute !== null &&
        Number.isFinite(Number(apt.target_minute))
      ) {
        const rawTargetMin = Number(apt.target_minute);
        const schedDay = Math.max(1, Number(apt.scheduled_day || currentDay) || currentDay);
        absMin = rawTargetMin >= 1440 ? rawTargetMin : (schedDay - 1) * 1440 + rawTargetMin;
      }
      if (absMin === null || absMin <= currentAbsMinute) return null;
      return {
        ...apt,
        _absMin: absMin,
        _displayName:
          apt.target_display_name ||
          apt.npc_name ||
          apt.partner_name ||
          apt.target_entity ||
          'contact',
      };
    })
    .filter(Boolean)
    .sort((a, b) => a._absMin - b._absMin);

  const upcomingAppointment =
    upcomingCommitments.find((apt) => apt._absMin <= targetAbsMinute) || null;
  const nextAppointment = upcomingCommitments[0] || null;

  const handleFastForwardToNextEvent = () => {
    if (isTemporalStasis || !nextAppointment?._absMin) return;
    const mortalDiff = nextAppointment._absMin - currentAbsMinute;
    const localDiff = isScaledTime ? Math.round(mortalDiff / timeScale) : mortalDiff;
    setSkipMinutes(clampSkipMinutes(localDiff));
    setMode('wait');
  };

  const adjustMinutes = (delta) => {
    setSkipMinutes((prev) => {
      if (prev % STEP_MINUTES !== 0) {
        const snapped =
          delta > 0
            ? Math.ceil(prev / STEP_MINUTES) * STEP_MINUTES
            : Math.floor(prev / STEP_MINUTES) * STEP_MINUTES;
        return clampSkipMinutes(snapped === prev ? snapped + delta : snapped);
      }
      return clampSkipMinutes(prev + delta);
    });
  };

  const handleSliderChange = (e) => {
    const raw = Number(e.target.value);
    if (!Number.isFinite(raw)) return;
    if (skipMinutes % STEP_MINUTES !== 0) {
      const snapped =
        raw > skipMinutes
          ? Math.ceil(raw / STEP_MINUTES) * STEP_MINUTES
          : Math.floor(raw / STEP_MINUTES) * STEP_MINUTES;
      setSkipMinutes(clampSkipMinutes(snapped));
      return;
    }
    setSkipMinutes(clampSkipMinutes(raw));
  };

  const handleConfirmSkip = async () => {
    if (processing || skipMinutes <= 0 || isWaitBlockedByStasis) return;
    const hours = (skipMinutes / 60).toFixed(1);
    const readableDuration =
      skipMinutes >= 60 ? `${hours} hours` : `${skipMinutes} minutes`;

    let customText = '';
    let intent = 'wait_time';
    let sleepMode = 'wait';

    if (effectiveAction === 'sleep') {
      const surf = sleepContext.surface_label
        ? sleepContext.surface_label.toLowerCase()
        : 'bed';
      customText = isTemporalStasis
        ? `I turn in on the ${surf} and sleep for ${readableDuration} while outside mortal time remains frozen.`
        : `I turn in for the night on the ${surf} and sleep until morning at ${targetTimePromptStr}.`;
      intent = 'rest_sleep';
      sleepMode = 'sleep';
    } else if (effectiveAction === 'nap') {
      const surf = sleepContext.surface_label
        ? sleepContext.surface_label.toLowerCase()
        : 'bed';
      customText = isTemporalStasis
        ? `I lie down on the ${surf} and take a ${readableDuration} nap while outside mortal time remains frozen.`
        : `I lie down on the ${surf} and take a ${readableDuration} nap until ${targetTimePromptStr}.`;
      intent = 'rest_sleep';
      sleepMode = 'nap';
    } else {
      customText = `I wait and pass the time for ${readableDuration} until Day ${targetDay} at ${targetTimePromptStr}.`;
      intent = 'wait_time';
      sleepMode = 'wait';
    }

    void Promise.resolve(
      onAction?.({
        custom_action_text: customText,
        intent,
        sleep_mode: sleepMode,
        skip_minutes: skipMinutes,
        target_day: targetDay,
        target_minute: targetNormMinute,
      })
    ).catch(() => {});
    onClose();
  };

  const durationPresets =
    canSleep && mode === 'rest'
      ? [
          { minutes: 60, label: '+1h' },
          { minutes: 120, label: '+2h' },
          { minutes: 360, label: '+6h' },
          { minutes: 480, label: '+8h' },
        ]
      : [
          { minutes: 15, label: '+15m' },
          { minutes: 60, label: '+1h' },
          { minutes: 180, label: '+3h' },
          { minutes: 360, label: '+6h' },
        ];

  const timeOfDayTargets = [
    {
      key: 'morning',
      minute: 450,
      label: t('timeskip.phase_morning', 'Morning'),
      Icon: Sunrise,
    },
    {
      key: 'noon',
      minute: 720,
      label: t('timeskip.phase_noon', 'Noon'),
      Icon: Sun,
    },
    {
      key: 'dusk',
      minute: 1080,
      label: t('timeskip.phase_dusk', 'Dusk'),
      Icon: Sunset,
    },
    {
      key: 'night',
      minute: 1260,
      label: t('timeskip.phase_night', 'Night'),
      Icon: Moon,
    },
  ];

  const ConfirmIcon =
    effectiveAction === 'sleep'
      ? Moon
      : effectiveAction === 'nap'
        ? SurfaceIcon
        : Clock;
  const confirmLabel =
    effectiveAction === 'sleep'
      ? t('timeskip.confirm_sleep', {
          duration: compactDuration,
          defaultValue: 'Sleep · {{duration}}',
        })
      : effectiveAction === 'nap'
        ? t('timeskip.confirm_rest', {
            duration: compactDuration,
            defaultValue: 'Rest · {{duration}}',
          })
        : t('timeskip.confirm_wait', {
            duration: compactDuration,
            defaultValue: 'Wait · {{duration}}',
          });

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={onClose}
      label={t('timeskip.title', 'Time Skip')}
      maxWidthClass="max-w-md"
    >
      {/* Header */}
      <div className="px-4 sm:px-5 py-3.5 border-b border-fantasy-border/35 flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <Clock size={16} className="text-fantasy-accent shrink-0" aria-hidden="true" />
          <h2 className="font-rpg font-bold text-base text-gray-100 truncate">
            {t('timeskip.title', 'Time Skip')}
          </h2>
        </div>
        <MotionButton
          onClick={onClose}
          aria-label={t('common.close', 'Close')}
          className="hk-icon-btn h-8 min-w-8 shrink-0"
        >
          <X size={16} aria-hidden="true" />
        </MotionButton>
      </div>

      {/* Body */}
      <div className="px-4 sm:px-5 py-4 space-y-4 overflow-y-auto overscroll-contain custom-scrollbar select-none">
        {/* Hero Time Journey Surface */}
        <div className="rounded-2xl bg-gray-500/[0.08] border border-fantasy-border/35 px-4 py-3.5 space-y-3">
          <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2">
            {/* Current Time */}
            <div className="min-w-0 space-y-0.5">
              <div className="text-[11px] text-gray-400 truncate">
                {currentDayLabel}
              </div>
              <div className="text-base sm:text-lg font-semibold text-gray-300 tabular-nums whitespace-nowrap">
                {currentTimeStr}
              </div>
              <div className="flex items-center gap-1 text-[11px] text-gray-400">
                <CurrentPhaseIcon
                  size={12}
                  className={`${currentPhase.colorClass} shrink-0`}
                  aria-hidden="true"
                />
                <span className="truncate">{currentPhase.label}</span>
              </div>
            </div>

            {/* Skip Delta Badge */}
            <div className="flex flex-col items-center justify-center gap-1 px-1">
              <span className="hk-chip hk-chip-accent tabular-nums">
                +{compactDuration}
              </span>
              <ArrowRight size={13} className="text-gray-500" aria-hidden="true" />
            </div>

            {/* Target Arrival Time */}
            <div className="min-w-0 text-right space-y-0.5">
              <div className="text-[11px] text-gray-300 flex items-center justify-end gap-1.5">
                <span className="truncate">{targetDayLabel}</span>
                {targetDayOffset > 0 && (
                  <span className="text-[10px] font-semibold px-1.5 py-px rounded-full bg-fantasy-accent/15 text-fantasy-accent tabular-nums shrink-0">
                    +{targetDayOffset}d
                  </span>
                )}
              </div>
              <div className="text-xl sm:text-2xl font-bold text-gray-50 tabular-nums whitespace-nowrap leading-tight">
                {targetTimeStr}
              </div>
              <div
                className={`flex items-center justify-end gap-1 text-[11px] font-medium ${targetPhase.colorClass}`}
              >
                <TargetPhaseIcon size={12} className="shrink-0" aria-hidden="true" />
                <span className="truncate">{targetPhase.label}</span>
              </div>
            </div>
          </div>

          {/* 24h Day-Cycle Indicator Bar (slider mode only; dial already shows 24h cycle) */}
          {!useAnalogDial && (
            <div className="relative h-1.5 rounded-full bg-gray-500/20 overflow-visible" aria-hidden="true">
              <div
                className="absolute inset-0 rounded-full opacity-55"
                style={{
                  background:
                    'linear-gradient(to right, oklch(0.26 0.05 265) 0%, oklch(0.68 0.12 75) 26%, oklch(0.84 0.13 85) 50%, oklch(0.62 0.14 45) 75%, oklch(0.26 0.05 265) 100%)',
                }}
              />
              <span
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-2 h-2 rounded-full bg-gray-200/80 ring-1 ring-black/40"
                style={{ left: `${currentDayPct}%` }}
              />
              <span
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 w-3 h-3 rounded-full bg-fantasy-accent ring-2 ring-fantasy-panel shadow-sm transition-[left] duration-200"
                style={{ left: `${targetDayPct}%` }}
              />
            </div>
          )}
        </div>

        {/* Temporal Stasis / Realm Time Scale Notice */}
        {(isTemporalStasis || isScaledTime) && (
          <div
            className={`rounded-xl px-3 py-2 border text-xs flex items-center gap-2 ${
              isTemporalStasis
                ? 'bg-cyan-500/12 border-cyan-400/35 text-cyan-200'
                : 'bg-fantasy-accent/10 border-fantasy-accent/25 text-gray-200'
            }`}
          >
            <Hourglass
              size={14}
              className={
                isTemporalStasis ? 'text-cyan-300 shrink-0' : 'text-fantasy-accent shrink-0'
              }
              aria-hidden="true"
            />
            <span>
              {isTemporalStasis
                ? t(
                    'timeskip.temporal_stasis_banner',
                    'Temporal Stasis — mortal time outside stands still while you rest.'
                  )
                : t('timeskip.time_scale_note', {
                    scale: timeScale,
                    time: targetTimeStr,
                    defaultValue:
                      'Realm time scale {{scale}}× — mortal clock advances to {{time}}.',
                  })}
            </span>
          </div>
        )}

        {/* Mode & Rest Context */}
        {canSleep ? (
          <div className="space-y-1.5">
            <div
              role="group"
              aria-label={t('timeskip.mode_group_aria', 'Time skip mode')}
              className="hk-segmented"
            >
              <button
                type="button"
                aria-pressed={mode === 'rest'}
                onClick={() => {
                  setMode('rest');
                  if (skipMinutes < 30) setSkipMinutes(60);
                }}
              >
                <SurfaceIcon size={14} className="text-fantasy-accent shrink-0" aria-hidden="true" />
                <span>{t('timeskip.mode_rest', 'Rest')}</span>
                {recoveryPreview.hpPercent > 0 && (
                  <span className="text-[11px] font-semibold text-fantasy-accent tabular-nums">
                    +{recoveryPreview.hpPercent}%
                  </span>
                )}
              </button>
              <button
                type="button"
                aria-pressed={mode === 'wait'}
                onClick={() => setMode('wait')}
              >
                <Hourglass size={13} className="shrink-0" aria-hidden="true" />
                <span>{t('timeskip.mode_wait', 'Wait')}</span>
              </button>
            </div>
            <p className="text-xs text-gray-400 px-0.5 leading-snug">
              {surfaceLabel} · {recoveryPreview.hint}
            </p>
          </div>
        ) : (
          <div className="flex items-start gap-2 text-xs text-gray-400 px-0.5 leading-snug">
            {sleepContext.blocked_by_anomaly ? (
              <>
                <AlertTriangle
                  size={14}
                  className="text-amber-400 shrink-0 mt-0.5"
                  aria-hidden="true"
                />
                <span>
                  <strong className="text-amber-300 font-semibold">{surfaceLabel}</strong>
                  {sleepContext.reason ? ` · ${sleepContext.reason}` : ''}
                </span>
              </>
            ) : (
              <>
                <Hourglass size={13} className="shrink-0 mt-0.5" aria-hidden="true" />
                <span>{t('timeskip.no_bed_wait_only', 'No bed nearby · Wait only')}</span>
              </>
            )}
          </div>
        )}

        {/* Duration Control: Interactive 24h Analog Dial or Horizontal Slider */}
        {useAnalogDial ? (
          <div className="flex items-center justify-center gap-4 py-1">
            <MotionButton
              onClick={() => adjustMinutes(-STEP_MINUTES)}
              disabled={skipMinutes <= MIN_SKIP_MINUTES}
              aria-label={t('timeskip.decrease_15m', 'Decrease by 15 minutes')}
              className="hk-icon-btn h-9 min-w-9 shrink-0 border border-fantasy-border/40 bg-gray-500/10 disabled:opacity-35"
            >
              <Minus size={15} aria-hidden="true" />
            </MotionButton>

            <AnalogClockDial
              currentMinute={currentMinute}
              skipMinutes={skipMinutes}
              minMinutes={MIN_SKIP_MINUTES}
              maxMinutes={MAX_SKIP_MINUTES}
              stepMinutes={STEP_MINUTES}
              clockFormat={clockFormat}
              targetPhase={targetPhase}
              ariaLabel={t(
                'timeskip.dial_aria',
                '24-hour time skip dial. Drag or use arrow keys to adjust.'
              )}
              ariaValueText={`${compactDuration}, ${targetDayLabel} ${targetTimeStr}`}
              onChange={setSkipMinutes}
            />

            <MotionButton
              onClick={() => adjustMinutes(STEP_MINUTES)}
              disabled={skipMinutes >= MAX_SKIP_MINUTES}
              aria-label={t('timeskip.increase_15m', 'Increase by 15 minutes')}
              className="hk-icon-btn h-9 min-w-9 shrink-0 border border-fantasy-border/40 bg-gray-500/10 disabled:opacity-35"
            >
              <Plus size={15} aria-hidden="true" />
            </MotionButton>
          </div>
        ) : (
          <div className="space-y-1">
            <label htmlFor={sliderId} className="sr-only">
              {t('timeskip.duration_label', 'Skip duration')}
            </label>
            <div className="flex items-center gap-2">
              <MotionButton
                onClick={() => adjustMinutes(-STEP_MINUTES)}
                disabled={skipMinutes <= MIN_SKIP_MINUTES}
                aria-label={t('timeskip.decrease_15m', 'Decrease by 15 minutes')}
                className="hk-icon-btn h-8 min-w-8 shrink-0 border border-fantasy-border/40 bg-gray-500/10 disabled:opacity-35"
              >
                <Minus size={14} aria-hidden="true" />
              </MotionButton>

              <input
                id={sliderId}
                type="range"
                min={MIN_SKIP_MINUTES}
                max={MAX_SKIP_MINUTES}
                step={skipMinutes % STEP_MINUTES === 0 ? STEP_MINUTES : 1}
                value={skipMinutes}
                aria-valuetext={`${compactDuration}, ${targetDayLabel} ${targetTimeStr}`}
                onChange={handleSliderChange}
                style={{
                  '--attr-min': MIN_SKIP_MINUTES,
                  '--attr-max': MAX_SKIP_MINUTES,
                  '--control-value': skipMinutes,
                }}
                className="hk-slider flex-1 min-w-0"
              />

              <MotionButton
                onClick={() => adjustMinutes(STEP_MINUTES)}
                disabled={skipMinutes >= MAX_SKIP_MINUTES}
                aria-label={t('timeskip.increase_15m', 'Increase by 15 minutes')}
                className="hk-icon-btn h-8 min-w-8 shrink-0 border border-fantasy-border/40 bg-gray-500/10 disabled:opacity-35"
              >
                <Plus size={14} aria-hidden="true" />
              </MotionButton>
            </div>
            <div className="flex justify-between px-10 text-[10px] text-gray-500 tabular-nums">
              <span>15m</span>
              <span>8h</span>
              <span>16h</span>
              <span>24h</span>
            </div>
          </div>
        )}

        {/* Compact Quick-Pick Grid (2 rows: durations + time of day) */}
        <div className="space-y-2">
          <div
            role="group"
            aria-label={t('timeskip.quick_durations_aria', 'Quick durations')}
            className="grid grid-cols-4 gap-1.5"
          >
            {durationPresets.map((preset) => {
              const active = skipMinutes === preset.minutes;
              return (
                <button
                  key={preset.minutes}
                  type="button"
                  aria-pressed={active}
                  onClick={() => setSkipMinutes(preset.minutes)}
                  className={`py-1.5 px-2 rounded-xl border text-xs font-semibold tabular-nums transition-colors ${
                    active
                      ? 'bg-fantasy-accent/15 border-fantasy-accent/60 text-fantasy-accent'
                      : 'bg-gray-500/10 border-fantasy-border/35 text-gray-200 hover:bg-gray-500/20 hover:border-fantasy-border/70'
                  }`}
                >
                  {preset.label}
                </button>
              );
            })}
          </div>

          <div
            role="group"
            aria-label={t('timeskip.jump_to_time_aria', 'Jump to time of day')}
            className="grid grid-cols-4 gap-1.5"
          >
            {timeOfDayTargets.map((target) => {
              const mortalDiff = computeDiffToClockMinute(currentMinute, target.minute);
              const diff = isScaledTime
                ? clampSkipMinutes(Math.round(mortalDiff / timeScale))
                : mortalDiff;
              const active = !isTemporalStasis && skipMinutes === diff;
              const TargetIcon = target.Icon;
              return (
                <button
                  key={target.key}
                  type="button"
                  disabled={isTemporalStasis}
                  aria-pressed={active}
                  onClick={() => !isTemporalStasis && setSkipMinutes(diff)}
                  className={`py-1.5 px-2 rounded-xl border text-xs font-semibold flex items-center justify-center gap-1.5 min-w-0 transition-colors ${
                    isTemporalStasis
                      ? 'bg-gray-500/5 border-fantasy-border/20 text-gray-500 cursor-not-allowed opacity-50'
                      : active
                        ? 'bg-fantasy-accent/15 border-fantasy-accent/60 text-fantasy-accent'
                        : 'bg-gray-500/10 border-fantasy-border/35 text-gray-200 hover:bg-gray-500/20 hover:border-fantasy-border/70'
                  }`}
                >
                  <TargetIcon size={12} className="shrink-0" aria-hidden="true" />
                  <span className="truncate">{target.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Appointment Warning */}
        {upcomingAppointment && (
          <div className="rounded-xl px-3 py-2.5 bg-rose-500/12 border border-rose-500/35 text-rose-200 text-xs flex items-center justify-between gap-2.5">
            <div className="flex items-center gap-2 min-w-0">
              <AlertTriangle size={14} className="text-rose-400 shrink-0" aria-hidden="true" />
              <span className="leading-snug">
                {t('timeskip.meetup_warning', {
                  name: upcomingAppointment._displayName,
                  time: formatClockTime(upcomingAppointment._absMin % 1440, clockFormat),
                  defaultValue: 'Plans with {{name}} at {{time}}',
                })}
              </span>
            </div>
            {nextAppointment && !isTemporalStasis && (
              <button
                type="button"
                onClick={handleFastForwardToNextEvent}
                className="shrink-0 px-2.5 py-1 rounded-lg bg-rose-500/20 hover:bg-rose-500/30 border border-rose-400/45 text-rose-100 font-semibold text-[11px] transition-colors"
              >
                {t('timeskip.catch_meetup', 'Jump to it')}
              </button>
            )}
          </div>
        )}

        {/* Multiplayer Note */}
        {isMultiplayer && (
          <div className="rounded-xl px-3 py-2 bg-fantasy-accent/10 border border-fantasy-accent/25 text-xs text-gray-300 flex items-center gap-2">
            <Users size={14} className="text-fantasy-accent shrink-0" aria-hidden="true" />
            <span>
              {t(
                'timeskip.multiplayer_note',
                'Party session · Requests a group time skip.'
              )}
            </span>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="px-4 sm:px-5 py-3 border-t border-fantasy-border/35 flex items-center justify-between gap-2 shrink-0">
        <MotionButton onClick={onClose} className="hk-btn hk-btn-ghost">
          {t('timeskip.cancel', 'Cancel')}
        </MotionButton>
        <MotionButton
          disabled={processing || skipMinutes <= 0 || isWaitBlockedByStasis}
          onClick={handleConfirmSkip}
          className="hk-btn hk-btn-primary"
        >
          <ConfirmIcon size={14} aria-hidden="true" />
          <span className="tabular-nums">{confirmLabel}</span>
        </MotionButton>
      </div>
    </AcrylicModal>
  );
};

export default TimeSkipModal;
