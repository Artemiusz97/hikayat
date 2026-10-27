import React, { useState, useMemo, useEffect } from 'react';
import { Clock, Moon, Sun, AlertTriangle, FastForward, Check, X, ShieldAlert, Sparkles, Users } from 'lucide-react';

const formatClockTime = (totalMinutes) => {
  const normalized = ((totalMinutes % 1440) + 1440) % 1440;
  const hours = Math.floor(normalized / 60);
  const minutes = normalized % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}`;
};

const getTimePhase = (minute) => {
  const norm = ((minute % 1440) + 1440) % 1440;
  if (norm >= 300 && norm < 420) return { label: 'Dawn', icon: '🌅', color: 'text-amber-300' };
  if (norm >= 420 && norm < 720) return { label: 'Morning', icon: '☀️', color: 'text-yellow-300' };
  if (norm >= 720 && norm < 1080) return { label: 'Afternoon', icon: '🌤️', color: 'text-amber-200' };
  if (norm >= 1080 && norm < 1200) return { label: 'Dusk', icon: '🌇', color: 'text-orange-400' };
  return { label: 'Night', icon: '🌙', color: 'text-indigo-300' };
};

const TimeSkipModal = ({
  isOpen,
  onClose,
  session,
  phoneHook,
  onAction,
  processing
}) => {
  // Current time parsed from session
  const currentDay = Number(session?.current_day || 1);
  const currentMinute = Number(session?.current_minute !== undefined ? session.current_minute : 480); // default 08:00 AM

  // Sleep surface context
  const sleepContext = useMemo(() => {
    return session?.sleep_context || {
      surface: 'camp',
      can_sleep: true,
      recovery_ratio: 1.0,
      surface_label: 'Camp',
      reason: 'Resting available.'
    };
  }, [session?.sleep_context]);

  const canSleep = Boolean(sleepContext.can_sleep);
  const surface = sleepContext.surface || (canSleep ? 'bed' : 'none');
  const recoveryRatio = sleepContext.recovery_ratio !== undefined ? sleepContext.recovery_ratio : (canSleep ? 1.0 : 0.0);

  // Selected duration to skip in minutes (default +120m / 2 hours)
  const [skipMinutes, setSkipMinutes] = useState(120);
  const [mode, setMode] = useState('auto'); // 'auto', 'sleep', 'nap', 'wait'

  useEffect(() => {
    if (!canSleep) {
      setMode('wait');
    } else if (mode === 'wait') {
      setMode('auto');
    }
  }, [canSleep, isOpen]);

  // Recovery preview based on surface and duration (placed before early return to satisfy Rules of Hooks)
  const recoveryPreview = useMemo(() => {
    if (!canSleep || mode === 'wait') {
      return { hpPercent: 0, label: '0% Recovery (Time passes only)' };
    }
    const isFullSleep = mode === 'sleep' || (mode === 'auto' && skipMinutes >= 360);
    if (isFullSleep) {
      const pct = Math.round(recoveryRatio * 100);
      return { hpPercent: pct, label: `${pct}% HP/MP Full Rest • Clears Fatigue` };
    }
    const napFraction = Math.min(1.0, skipMinutes / 480);
    const pct = Math.round(napFraction * recoveryRatio * 100);
    return { hpPercent: pct, label: `+${pct}% HP/MP Nap Rest` };
  }, [canSleep, mode, skipMinutes, recoveryRatio]);

  if (!isOpen) return null;

  const targetMinute = currentMinute + skipMinutes;
  const targetDayOffset = Math.floor(targetMinute / 1440);
  const targetDay = currentDay + targetDayOffset;
  const targetTimeStr = formatClockTime(targetMinute);
  const currentTimeStr = formatClockTime(currentMinute);
  const targetPhase = getTimePhase(targetMinute);
  const currentPhase = getTimePhase(currentMinute);

  const isMultiplayer = Boolean(session?.party_members && session.party_members.length > 1);

  // Check for upcoming appointments from phoneHook
  const appointments = phoneHook?.appointments || [];
  const upcomingAppointment = appointments.find((apt) => {
    if (!apt.target_minute) return false;
    return apt.target_minute > currentMinute && apt.target_minute <= targetMinute;
  });

  const nextAppointment = appointments
    .filter((a) => a.target_minute && a.target_minute > currentMinute)
    .sort((a, b) => a.target_minute - b.target_minute)[0];

  const handleFastForwardToNextEvent = () => {
    if (nextAppointment?.target_minute) {
      const diff = Math.max(15, nextAppointment.target_minute - currentMinute);
      setSkipMinutes(diff);
      setMode('wait');
    }
  };

  const handleConfirmSkip = async () => {
    if (processing) return;
    const hours = (skipMinutes / 60).toFixed(1);
    const readableDuration = skipMinutes >= 60 ? `${hours} hours` : `${skipMinutes} minutes`;

    const isFullSleep = canSleep && (mode === 'sleep' || (mode === 'auto' && skipMinutes >= 360));
    const isNap = canSleep && (mode === 'nap' || (mode === 'auto' && skipMinutes < 360 && skipMinutes >= 30));

    let customText = "";
    let intent = "wait_time";
    let sleepMode = "wait";

    if (isFullSleep) {
      const surf = sleepContext.surface_label ? sleepContext.surface_label.toLowerCase() : "bed";
      customText = `I turn in for the night on the ${surf} and sleep until morning at ${targetTimeStr}.`;
      intent = "rest_sleep";
      sleepMode = "sleep";
    } else if (isNap) {
      const surf = sleepContext.surface_label ? sleepContext.surface_label.toLowerCase() : "bed";
      customText = `I lie down on the ${surf} and take a ${readableDuration} nap until ${targetTimeStr}.`;
      intent = "rest_sleep";
      sleepMode = "nap";
    } else {
      customText = `I wait and pass the time for ${readableDuration} until Day ${targetDay} at ${targetTimeStr}.`;
      intent = "wait_time";
      sleepMode = "wait";
    }

    await onAction({
      custom_action_text: customText,
      intent,
      sleep_mode: sleepMode,
      skip_minutes: skipMinutes,
      target_day: targetDay,
      target_minute: targetMinute % 1440
    });
    onClose();
  };

  // Genshin-style dial angle calculation
  const targetHourFrac = ((targetMinute % 1440) / 1440) * 360;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 bg-black/75 backdrop-blur-md animate-in fade-in duration-200 select-none">
      <div className="fixed inset-0" onClick={onClose} />
      <div className="relative w-full max-w-lg max-h-[calc(var(--app-height,100dvh)-1.5rem)] overflow-y-auto overflow-x-hidden overscroll-contain custom-scrollbar bg-fantasy-panel border border-amber-500/40 rounded-2xl shadow-2xl p-4 sm:p-5 space-y-4 z-10">
        
        {/* Glow backdrop effect */}
        <div className="absolute -top-16 -left-16 w-48 h-48 bg-amber-500/10 rounded-full blur-3xl pointer-events-none" />
        <div className="absolute -bottom-16 -right-16 w-48 h-48 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none" />

        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-fantasy-border/60 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-full bg-amber-500/20 border border-amber-500/40 flex items-center justify-center text-amber-300">
              <Clock size={16} />
            </div>
            <div>
              <h3 className="font-rpg font-bold text-fantasy-accent text-base leading-tight">
                Chronos Dial • Time Skip
              </h3>
              <p className="text-[11px] text-gray-400">
                Turn the hands of time to advance the world and regain energy
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-gray-400 hover:text-gray-200 rounded-lg hover:bg-white/10 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Genshin-Style Clock Face & Progression Display */}
        <div className="flex flex-col sm:flex-row items-center justify-around gap-4 bg-black/50 border border-fantasy-border/80 rounded-xl p-4 shadow-inner">
          {/* Animated Clock Dial */}
          <div className="relative w-36 h-36 rounded-full border-2 border-amber-500/30 flex items-center justify-center bg-gradient-to-b from-neutral-900 to-black shadow-lg shrink-0">
            {/* Clock Face Markers */}
            <div className="absolute top-2 text-[10px] font-mono font-bold text-amber-400">12</div>
            <div className="absolute bottom-2 text-[10px] font-mono font-bold text-indigo-400">24</div>
            <div className="absolute right-2 text-[10px] font-mono font-bold text-amber-300">06</div>
            <div className="absolute left-2 text-[10px] font-mono font-bold text-orange-400">18</div>
            
            {/* Center Dial Hub */}
            <div className="w-4 h-4 rounded-full bg-amber-400 z-10 shadow-[0_0_10px_rgba(245,158,11,0.8)]" />

            {/* Rotating Hand Pointer */}
            <div
              className="absolute w-1 h-14 bg-gradient-to-t from-amber-400 to-amber-200 rounded-full origin-bottom transition-transform duration-300 ease-out shadow-md"
              style={{
                bottom: '50%',
                transform: `rotate(${targetHourFrac}deg)`
              }}
            />

            {/* Sun / Moon Orbit Badge */}
            <div
              className="absolute w-6 h-6 rounded-full bg-black/80 border border-amber-400 flex items-center justify-center text-xs shadow-md transition-all duration-300"
              style={{
                transform: `rotate(${targetHourFrac}deg) translateY(-58px) rotate(-${targetHourFrac}deg)`
              }}
            >
              {targetPhase.icon}
            </div>
          </div>

          {/* Time Progression Summary */}
          <div className="flex-1 min-w-0 space-y-2.5 text-center sm:text-left">
            <div>
              <span className="text-[10px] uppercase font-mono font-bold text-gray-400 tracking-wider">
                Current Time
              </span>
              <div className="font-mono text-sm text-gray-300 font-semibold flex items-center justify-center sm:justify-start gap-1.5">
                <span>{currentPhase.icon}</span>
                <span>Day {currentDay} • {currentTimeStr}</span>
                <span className={`text-[10px] font-mono uppercase ${currentPhase.color}`}>({currentPhase.label})</span>
              </div>
            </div>

            <div className="text-amber-400 font-bold text-xs flex items-center justify-center sm:justify-start gap-1">
              <FastForward size={13} />
              <span>Advancing +{(skipMinutes / 60).toFixed(1)} hrs ({skipMinutes} mins)</span>
            </div>

            <div className="p-2 rounded-lg bg-amber-950/40 border border-amber-500/40">
              <span className="text-[10px] uppercase font-mono font-bold text-amber-300 tracking-wider">
                Projected Arrival
              </span>
              <div className="font-mono text-base font-extrabold text-amber-200 flex items-center justify-center sm:justify-start gap-1.5">
                <span>{targetPhase.icon}</span>
                <span>Day {targetDay} • {targetTimeStr}</span>
                <span className={`text-xs ${targetPhase.color}`}>[{targetPhase.label}]</span>
              </div>
            </div>
          </div>
        </div>

        {/* Sleeping Surface & Recovery Indicator */}
        <div className={`p-2.5 rounded-xl border flex items-center justify-between gap-3 text-xs ${
          canSleep
            ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
            : 'bg-neutral-900/60 border-neutral-700/60 text-gray-300'
        }`}>
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-base shrink-0">
              {surface === 'bed' ? '🛏️' : (surface === 'couch' ? '🛋️' : (surface === 'camp' ? '🏕️' : '⏳'))}
            </span>
            <div className="min-w-0">
              <div className="font-bold truncate">
                Surface: {sleepContext.surface_label || (canSleep ? 'Bed' : 'None in vicinity')}
              </div>
              <div className="text-[11px] text-gray-400 truncate">
                {sleepContext.reason}
              </div>
            </div>
          </div>
          <div className="shrink-0 px-2 py-1 rounded bg-black/50 border border-amber-500/30 text-right">
            <span className="font-mono text-[11px] font-bold text-amber-300 block">
              {recoveryPreview.label}
            </span>
          </div>
        </div>

        {/* Interactive Time Slider */}
        <div className="space-y-1.5">
          <div className="flex justify-between items-center text-xs">
            <span className="font-mono font-bold text-gray-300">Skip Duration:</span>
            <span className="font-mono font-extrabold text-amber-300">
              {Math.floor(skipMinutes / 60)}h {skipMinutes % 60}m
            </span>
          </div>
          <input
            type="range"
            min="15"
            max="1440"
            step="15"
            value={skipMinutes}
            onChange={(e) => setSkipMinutes(Number(e.target.value))}
            className="w-full accent-amber-500 h-2 bg-black/60 rounded-lg cursor-pointer"
          />
          <div className="flex justify-between text-[10px] font-mono text-gray-500">
            <span>+15m</span>
            <span>+6h</span>
            <span>+12h</span>
            <span>+24h</span>
          </div>
        </div>

        {/* Quick Presets Grid */}
        <div className="space-y-1.5">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            {canSleep ? 'Quick Presets' : 'Quick Presets (Wait Mode • 0% Recovery)'}
          </span>
          {canSleep ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
              <button
                type="button"
                onClick={() => {
                  const curM = currentMinute % 1440;
                  const diff = curM < 450 ? 450 - curM : (1440 - curM) + 450;
                  setSkipMinutes(diff);
                  setMode('sleep');
                }}
                className="py-1.5 px-2 rounded-lg bg-indigo-950/40 hover:bg-indigo-900/60 border border-indigo-700/60 hover:border-indigo-400 text-xs font-semibold text-indigo-200 transition-all text-center"
              >
                🌙 Sleep to Morning
              </button>
              <button
                type="button"
                onClick={() => { setSkipMinutes(60); setMode('nap'); }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-amber-400/60 text-xs font-semibold text-amber-200 transition-all text-center"
              >
                ☕ 1h Nap
              </button>
              <button
                type="button"
                onClick={() => { setSkipMinutes(120); setMode('nap'); }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-amber-400/60 text-xs font-semibold text-amber-200 transition-all text-center"
              >
                🛌 2h Nap
              </button>
              <button
                type="button"
                onClick={() => { setSkipMinutes(60); setMode('wait'); }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-neutral-500 text-xs font-semibold text-gray-300 transition-all text-center"
              >
                ⏳ Wait 1 Hour
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-1.5">
              <button
                type="button"
                onClick={() => { setSkipMinutes(15); setMode('wait'); }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-neutral-500 text-xs font-semibold text-gray-200 transition-all text-center"
              >
                ⏳ Wait 15m
              </button>
              <button
                type="button"
                onClick={() => { setSkipMinutes(60); setMode('wait'); }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-neutral-500 text-xs font-semibold text-gray-200 transition-all text-center"
              >
                ⏳ Wait 1 Hour
              </button>
              <button
                type="button"
                onClick={() => { setSkipMinutes(180); setMode('wait'); }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-neutral-500 text-xs font-semibold text-gray-200 transition-all text-center"
              >
                ⏳ Wait 3 Hours
              </button>
              <button
                type="button"
                onClick={() => {
                  const curM = currentMinute % 1440;
                  const diff = curM < 360 ? 360 - curM : (1440 - curM) + 360;
                  setSkipMinutes(diff);
                  setMode('wait');
                }}
                className="py-1.5 px-2 rounded-lg bg-black/60 hover:bg-neutral-900 border border-fantasy-border hover:border-neutral-500 text-xs font-semibold text-gray-200 transition-all text-center"
              >
                🌅 Wait for Dawn
              </button>
            </div>
          )}
        </div>

        {/* Appointment Warning Guard */}
        {upcomingAppointment && (
          <div className="p-2.5 rounded-xl bg-rose-950/70 border border-rose-600/80 text-rose-200 text-xs flex items-center justify-between gap-2 shadow-sm animate-pulse">
            <div className="flex items-center gap-2">
              <AlertTriangle size={16} className="text-rose-400 shrink-0" />
              <span>
                <strong>Warning:</strong> You have an upcoming date with {upcomingAppointment.partner_name || 'contact'} at {formatClockTime(upcomingAppointment.target_minute)}!
              </span>
            </div>
            {nextAppointment && (
              <button
                type="button"
                onClick={handleFastForwardToNextEvent}
                className="shrink-0 px-2.5 py-1 rounded bg-rose-900 hover:bg-rose-800 text-rose-100 font-bold text-[11px] border border-rose-400/60 transition-colors"
              >
                Catch Meetup
              </button>
            )}
          </div>
        )}

        {/* Multiplayer note */}
        {isMultiplayer && (
          <div className="flex items-center gap-2 text-xs text-amber-300/90 bg-amber-950/40 border border-amber-700/50 p-2 rounded-lg font-mono">
            <Users size={14} className="shrink-0" />
            <span>Multiplayer Party Session: Submitting this will request a party time skip.</span>
          </div>
        )}

        {/* Footer Confirm & Cancel */}
        <div className="flex items-center justify-between pt-2 border-t border-fantasy-border/60">
          <button
            type="button"
            onClick={onClose}
            className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-gray-400 hover:text-white hover:bg-white/5 transition-colors"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={processing || skipMinutes <= 0}
            onClick={handleConfirmSkip}
            className="px-5 py-2 rounded-xl bg-gradient-to-r from-amber-500 to-amber-600 hover:from-amber-400 hover:to-amber-500 text-black font-extrabold text-xs shadow-lg hover:shadow-amber-500/30 transition-all flex items-center gap-1.5 disabled:opacity-50"
          >
            <Clock size={14} />
            <span>Confirm Time Skip</span>
          </button>
        </div>

      </div>
    </div>
  );
};

export default TimeSkipModal;
