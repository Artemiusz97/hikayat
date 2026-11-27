import { useRef, useState } from 'react';
import { normalizeMinute } from '../../utils/timeFormat';

const DIAL_CX = 100;
const DIAL_CY = 100;
const TRACK_RADIUS = 72;

const minuteToDialAngle = (minute) =>
  ((normalizeMinute(minute) / 1440) * 360 + 180) % 360;

const polarToCartesian = (cx, cy, radius, angleDeg) => {
  const rad = (angleDeg * Math.PI) / 180;
  return {
    x: cx + radius * Math.sin(rad),
    y: cy - radius * Math.cos(rad),
  };
};

const describeClockwiseArc = (cx, cy, radius, startDeg, sweepDeg) => {
  const start = polarToCartesian(cx, cy, radius, startDeg);
  const end = polarToCartesian(cx, cy, radius, startDeg + sweepDeg);
  const largeArc = sweepDeg > 180 ? 1 : 0;
  return `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${radius} ${radius} 0 ${largeArc} 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;
};

const getPointerDialAngle = (clientX, clientY, rect) => {
  const dx = clientX - (rect.left + rect.width / 2);
  const dy = clientY - (rect.top + rect.height / 2);
  return ((Math.atan2(dx, -dy) * 180) / Math.PI + 360) % 360;
};

const HOUR_TICKS = Array.from({ length: 24 }, (_, hour) => {
  const angle = ((hour / 24) * 360 + 180) % 360;
  const isCardinal = hour % 6 === 0;
  const inner = polarToCartesian(DIAL_CX, DIAL_CY, isCardinal ? 82 : 84, angle);
  const outer = polarToCartesian(DIAL_CX, DIAL_CY, 90, angle);
  return {
    hour,
    isCardinal,
    x1: inner.x,
    y1: inner.y,
    x2: outer.x,
    y2: outer.y,
  };
});

const AnalogClockDial = ({
  currentMinute,
  skipMinutes,
  minMinutes = 15,
  maxMinutes = 1440,
  stepMinutes = 15,
  clockFormat = '24h',
  targetPhase,
  ariaLabel,
  ariaValueText,
  onChange,
}) => {
  const dragRef = useRef({
    active: false,
    lastAngle: 0,
    rawMinutes: skipMinutes,
  });
  const [isDragging, setIsDragging] = useState(false);

  const clampValue = (mins) =>
    Math.max(minMinutes, Math.min(maxMinutes, Math.round(mins)));

  const snapValue = (mins) =>
    clampValue(Math.round(mins / stepMinutes) * stepMinutes);

  const startAngle = minuteToDialAngle(currentMinute);
  const sweepDeg = Math.min(
    360,
    Math.max(0, (skipMinutes / maxMinutes) * 360)
  );
  const targetAngle = (startAngle + sweepDeg) % 360;

  const startDot = polarToCartesian(DIAL_CX, DIAL_CY, TRACK_RADIUS, startAngle);
  const handlePoint = polarToCartesian(
    DIAL_CX,
    DIAL_CY,
    TRACK_RADIUS,
    targetAngle
  );
  const handEnd = polarToCartesian(
    DIAL_CX,
    DIAL_CY,
    TRACK_RADIUS - 11,
    targetAngle
  );

  const TargetPhaseIcon = targetPhase?.Icon;
  const isFullDaySweep = skipMinutes >= maxMinutes;

  const cardinals =
    clockFormat === '12h'
      ? { top: '12P', right: '6P', bottom: '12A', left: '6A' }
      : { top: '12', right: '18', bottom: '00', left: '06' };

  const handlePointerDown = (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    e.preventDefault();
    const el = e.currentTarget;
    el.focus({ preventScroll: true });
    el.setPointerCapture(e.pointerId);

    const rect = el.getBoundingClientRect();
    const clickAngle = getPointerDialAngle(e.clientX, e.clientY, rect);
    const angularDist = Math.abs(
      ((clickAngle - targetAngle + 540) % 360) - 180
    );

    if (angularDist <= 22) {
      dragRef.current = {
        active: true,
        lastAngle: clickAngle,
        rawMinutes: skipMinutes,
      };
    } else {
      const cwDeg = (clickAngle - startAngle + 360) % 360;
      const jumpedRaw = (cwDeg / 360) * maxMinutes;
      const snapped = snapValue(jumpedRaw);
      dragRef.current = {
        active: true,
        lastAngle: clickAngle,
        rawMinutes: snapped,
      };
      onChange?.(snapped);
    }
    setIsDragging(true);
  };

  const handlePointerMove = (e) => {
    if (!dragRef.current.active || !e.currentTarget.hasPointerCapture(e.pointerId)) {
      return;
    }
    const rect = e.currentTarget.getBoundingClientRect();
    const angle = getPointerDialAngle(e.clientX, e.clientY, rect);
    let deltaDeg = angle - dragRef.current.lastAngle;
    if (deltaDeg > 180) deltaDeg -= 360;
    if (deltaDeg < -180) deltaDeg += 360;

    const nextRaw = Math.max(
      minMinutes,
      Math.min(maxMinutes, dragRef.current.rawMinutes + (deltaDeg / 360) * maxMinutes)
    );
    dragRef.current.lastAngle = angle;
    dragRef.current.rawMinutes = nextRaw;

    const snapped = snapValue(nextRaw);
    if (snapped !== skipMinutes) {
      onChange?.(snapped);
    }
  };

  const endDrag = () => {
    dragRef.current.active = false;
    setIsDragging(false);
  };

  const handleKeyDown = (e) => {
    let next = null;
    if (e.key === 'ArrowRight' || e.key === 'ArrowUp') {
      next =
        skipMinutes % stepMinutes !== 0
          ? clampValue(Math.ceil(skipMinutes / stepMinutes) * stepMinutes)
          : clampValue(skipMinutes + stepMinutes);
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowDown') {
      next =
        skipMinutes % stepMinutes !== 0
          ? clampValue(Math.floor(skipMinutes / stepMinutes) * stepMinutes)
          : clampValue(skipMinutes - stepMinutes);
    } else if (e.key === 'PageUp') {
      next = clampValue(skipMinutes + 60);
    } else if (e.key === 'PageDown') {
      next = clampValue(skipMinutes - 60);
    } else if (e.key === 'Home') {
      next = minMinutes;
    } else if (e.key === 'End') {
      next = maxMinutes;
    }

    if (next !== null) {
      e.preventDefault();
      onChange?.(next);
    }
  };

  return (
    <div
      role="slider"
      tabIndex={0}
      aria-label={ariaLabel}
      aria-valuemin={minMinutes}
      aria-valuemax={maxMinutes}
      aria-valuenow={skipMinutes}
      aria-valuetext={ariaValueText}
      onPointerDown={handlePointerDown}
      onPointerMove={handlePointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={endDrag}
      onKeyDown={handleKeyDown}
      className={`hk-dial-interactive relative w-44 h-44 sm:w-48 sm:h-48 rounded-full shrink-0 flex items-center justify-center ${
        isDragging ? 'is-dragging' : ''
      }`}
    >
      <svg
        viewBox="0 0 200 200"
        className="w-full h-full overflow-visible pointer-events-none"
        aria-hidden="true"
      >
        <circle
          cx={DIAL_CX}
          cy={DIAL_CY}
          r={92}
          fill="oklch(var(--bg-deep) / 0.55)"
          stroke="oklch(var(--border) / 0.55)"
          strokeWidth="1.5"
        />

        {HOUR_TICKS.map((tick) => (
          <line
            key={tick.hour}
            x1={tick.x1}
            y1={tick.y1}
            x2={tick.x2}
            y2={tick.y2}
            stroke={
              tick.isCardinal
                ? 'oklch(var(--g-300) / 0.65)'
                : 'oklch(var(--g-500) / 0.35)'
            }
            strokeWidth={tick.isCardinal ? '2' : '1.25'}
            strokeLinecap="round"
          />
        ))}

        <circle
          cx={DIAL_CX}
          cy={DIAL_CY}
          r={TRACK_RADIUS}
          fill="none"
          stroke="oklch(var(--g-500) / 0.22)"
          strokeWidth="6"
        />

        {isFullDaySweep ? (
          <circle
            cx={DIAL_CX}
            cy={DIAL_CY}
            r={TRACK_RADIUS}
            fill="none"
            stroke="oklch(var(--accent))"
            strokeWidth="6"
          />
        ) : (
          sweepDeg > 0.5 && (
            <path
              d={describeClockwiseArc(
                DIAL_CX,
                DIAL_CY,
                TRACK_RADIUS,
                startAngle,
                sweepDeg
              )}
              fill="none"
              stroke="oklch(var(--accent))"
              strokeWidth="6"
              strokeLinecap="round"
            />
          )
        )}

        <line
          x1={DIAL_CX}
          y1={DIAL_CY}
          x2={handEnd.x}
          y2={handEnd.y}
          stroke="oklch(var(--accent) / 0.85)"
          strokeWidth="2.5"
          strokeLinecap="round"
        />

        <circle
          cx={DIAL_CX}
          cy={DIAL_CY}
          r="5"
          fill="oklch(var(--accent))"
          stroke="oklch(var(--panel))"
          strokeWidth="2"
        />

        <circle
          cx={startDot.x}
          cy={startDot.y}
          r="3.75"
          fill="oklch(var(--g-200))"
          stroke="oklch(var(--panel))"
          strokeWidth="1.5"
        />
      </svg>

      {/* Cardinal 24h Labels */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute top-4 left-1/2 -translate-x-1/2 text-[10px] font-semibold tabular-nums text-amber-300/90"
      >
        {cardinals.top}
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute right-4 top-1/2 -translate-y-1/2 text-[10px] font-semibold tabular-nums text-orange-300/85"
      >
        {cardinals.right}
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute bottom-4 left-1/2 -translate-x-1/2 text-[10px] font-semibold tabular-nums text-indigo-300/85"
      >
        {cardinals.bottom}
      </span>
      <span
        aria-hidden="true"
        className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-[10px] font-semibold tabular-nums text-yellow-200/85"
      >
        {cardinals.left}
      </span>

      {/* Orbiting Target Handle */}
      <span
        aria-hidden="true"
        className={`pointer-events-none absolute -translate-x-1/2 -translate-y-1/2 w-7 h-7 rounded-full bg-fantasy-panel border-2 border-fantasy-accent shadow-md flex items-center justify-center ${
          isDragging ? '' : 'transition-[left,top] duration-150 ease-out'
        }`}
        style={{
          left: `${(handlePoint.x / 200) * 100}%`,
          top: `${(handlePoint.y / 200) * 100}%`,
        }}
      >
        {TargetPhaseIcon && (
          <TargetPhaseIcon
            size={13}
            className={targetPhase?.colorClass || 'text-fantasy-accent'}
            aria-hidden="true"
          />
        )}
      </span>
    </div>
  );
};

export default AnalogClockDial;
