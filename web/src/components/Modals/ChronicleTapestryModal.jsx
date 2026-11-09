import React, { useEffect, useId, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Award,
  ChevronLeft,
  ChevronRight,
  Crown,
  Flame,
  Globe,
  HeartHandshake,
  Infinity as InfinityIcon,
  ScrollText,
  Shield,
  X,
} from 'lucide-react';
import { cleanProseLocations } from '../../utils/locationFormat';

const SLIDE_ICONS = {
  world: Globe,
  factions: Shield,
  bonds: HeartHandshake,
  title: Crown,
};

const ChronicleTapestryModal = ({
  isOpen,
  onClose,
  tapestry,
  epilogueReady = false,
  busyAction = null,
  onChooseEpilogue,
}) => {
  const { t } = useTranslation();
  const dialogRef = useRef(null);
  const titleId = useId();
  const [slideIdx, setSlideIdx] = useState(0);

  const slides = Array.isArray(tapestry?.slides) ? tapestry.slides : [];
  const totalSlides = slides.length;
  const activeSlide = slides[Math.min(slideIdx, Math.max(0, totalSlides - 1))] || null;
  const endingId = tapestry?.ending_id || tapestry?.ending_archetype || '';
  const isFallenWorld = endingId === 'fallen_world' || Boolean(tapestry?.is_fallen_world);

  useEffect(() => {
    if (isOpen) {
      setSlideIdx(0);
    }
  }, [isOpen, endingId]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (isOpen && totalSlides > 0) {
      if (!dialog.open) {
        try {
          dialog.showModal();
        } catch {
          // Guard if already open in another state
        }
      }
    } else if (dialog.open) {
      dialog.close();
    }
  }, [isOpen, totalSlides]);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || typeof HTMLDialogElement === 'undefined') return undefined;
    if ('closedBy' in HTMLDialogElement.prototype) return undefined;

    const outside = (e) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };

    let pressedOutside = false;
    const onPointerDown = (e) => {
      pressedOutside = outside(e);
    };
    const onPointerUp = (e) => {
      if (pressedOutside && outside(e)) {
        dialog.close();
      }
      pressedOutside = false;
    };

    dialog.addEventListener('pointerdown', onPointerDown);
    dialog.addEventListener('pointerup', onPointerUp);
    return () => {
      dialog.removeEventListener('pointerdown', onPointerDown);
      dialog.removeEventListener('pointerup', onPointerUp);
    };
  }, []);

  const handleNativeClose = () => {
    const dialog = dialogRef.current;
    if (dialog) {
      dialog.returnValue = '';
    }
    if (onClose) {
      onClose();
    }
  };

  const requestClose = () => {
    const dialog = dialogRef.current;
    if (dialog?.open) {
      dialog.close();
    } else if (onClose) {
      onClose();
    }
  };

  if (!tapestry || totalSlides === 0) return null;

  const activeSlideId = activeSlide?.slide_id || activeSlide?.id || '';
  const SlideIcon = SLIDE_ICONS[activeSlideId] || ScrollText;

  return (
    <dialog
      ref={dialogRef}
      {...{ closedby: 'any' }}
      aria-labelledby={titleId}
      onClose={handleNativeClose}
      className="hk-chronicle-dialog rounded-xl shadow-2xl overflow-y-auto overflow-x-hidden custom-scrollbar"
    >
      <div
        className={`bg-fantasy-panel border rounded-xl p-4 sm:p-5 space-y-4 ${
          isFallenWorld
            ? 'border-rose-600/80 shadow-[0_0_32px_rgba(225,29,72,0.22)]'
            : 'border-fantasy-accent/80 shadow-[0_0_32px_rgba(201,162,94,0.2)]'
        }`}
      >
        {/* Header */}
        <div className="flex items-start justify-between gap-3 border-b border-fantasy-border/60 pb-3">
          <div className="space-y-1 min-w-0">
            <div className="flex items-center gap-1.5 flex-wrap">
              <span
                className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded border ${
                  isFallenWorld
                    ? 'bg-rose-950/70 text-rose-300 border-rose-600/60'
                    : 'bg-fantasy-accent/20 text-fantasy-accent border-fantasy-accent/40'
                }`}
              >
                {isFallenWorld
                  ? t('quests.fallen_resistance_badge', 'Fallen-World Chronicle')
                  : t('quests.chronicle_tapestry', 'Chronicle Tapestry')}
              </span>
              {tapestry.earned_title && (
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/60 text-amber-300 border border-amber-700/50">
                  🏅 {cleanProseLocations(tapestry.earned_title)}
                </span>
              )}
            </div>
            <h2
              id={titleId}
              className="font-rpg font-bold text-base sm:text-lg text-gray-100 leading-snug"
            >
              {cleanProseLocations(tapestry.ending_title || t('quests.chronicle_tapestry', 'Chronicle Tapestry'))}
            </h2>
          </div>

          <button
            type="button"
            onClick={requestClose}
            aria-label={t('common.close', 'Close')}
            className="p-1.5 text-gray-400 hover:text-gray-100 rounded-lg hover:bg-white/10 transition-colors shrink-0"
          >
            <X size={16} />
          </button>
        </div>

        {/* 4-Slide Stepper Tabs */}
        <div className="grid grid-cols-4 gap-1.5">
          {slides.map((sl, idx) => {
            const slKey = sl.slide_id || sl.id || idx;
            const IconComp = SLIDE_ICONS[sl.slide_id || sl.id] || ScrollText;
            const isSelected = idx === slideIdx;
            return (
              <button
                key={slKey}
                type="button"
                onClick={() => setSlideIdx(idx)}
                className={`flex flex-col items-center justify-center gap-1 py-2 px-1.5 rounded-lg border text-[10px] font-semibold transition-all ${
                  isSelected
                    ? isFallenWorld
                      ? 'bg-rose-950/60 text-rose-200 border-rose-500/70'
                      : 'bg-fantasy-accent/20 text-fantasy-accent border-fantasy-accent/60'
                    : 'bg-black/45 text-gray-400 border-fantasy-border/50 hover:text-gray-200 hover:bg-white/5'
                }`}
              >
                <IconComp size={13} />
                <span className="truncate max-w-full">{cleanProseLocations(sl.heading || `Slide ${idx + 1}`)}</span>
              </button>
            );
          })}
        </div>

        {/* Active Slide Content */}
        {activeSlide && (
          <div
            className={`rounded-xl border p-4 sm:p-5 space-y-3 min-h-[9.5rem] flex flex-col justify-between ${
              isFallenWorld
                ? 'bg-gradient-to-br from-rose-950/35 via-black/70 to-fantasy-dark border-rose-800/50'
                : 'bg-gradient-to-br from-fantasy-dark via-black/70 to-amber-950/20 border-fantasy-border/80'
            }`}
          >
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <SlideIcon
                    size={16}
                    className={isFallenWorld ? 'text-rose-400 shrink-0' : 'text-fantasy-accent shrink-0'}
                  />
                  <h3 className="font-rpg font-bold text-sm text-gray-100 uppercase tracking-wider">
                    {cleanProseLocations(activeSlide.heading)}
                  </h3>
                </div>
                <span className="text-[10px] font-mono text-gray-400">
                  {slideIdx + 1} / {totalSlides}
                </span>
              </div>

              <p className="text-xs sm:text-sm text-gray-200 leading-relaxed">
                {cleanProseLocations(activeSlide.text || activeSlide.body || '')}
              </p>
            </div>

            {activeSlideId === 'title' && tapestry.earned_title && (
              <div className="pt-2 border-t border-white/10 flex items-center gap-2 text-xs text-amber-300 font-semibold">
                <Award size={15} className="text-amber-400 shrink-0" />
                <span>
                  {t('quests.earned_epithet', 'Earned Epithet')}: <strong>{cleanProseLocations(tapestry.earned_title)}</strong>
                </span>
              </div>
            )}
          </div>
        )}

        {/* Carousel Navigation */}
        <div className="flex items-center justify-between gap-2 pt-1">
          <button
            type="button"
            disabled={slideIdx <= 0}
            onClick={() => setSlideIdx((prev) => Math.max(0, prev - 1))}
            className="flex items-center gap-1 px-3 py-1.5 rounded-lg bg-black/50 hover:bg-white/10 disabled:opacity-40 disabled:pointer-events-none text-xs font-semibold text-gray-200 border border-fantasy-border/70 transition-colors"
          >
            <ChevronLeft size={14} />
            <span>{t('quests.prev_slide', 'Previous')}</span>
          </button>

          {slideIdx < totalSlides - 1 ? (
            <button
              type="button"
              autoFocus
              onClick={() => setSlideIdx((prev) => Math.min(totalSlides - 1, prev + 1))}
              className="flex items-center gap-1 px-3.5 py-1.5 rounded-lg bg-fantasy-accent/25 hover:bg-fantasy-accent/40 text-fantasy-accent border border-fantasy-accent/60 text-xs font-bold transition-colors"
            >
              <span>{t('quests.next_slide', 'Next Slide')}</span>
              <ChevronRight size={14} />
            </button>
          ) : (
            <button
              type="button"
              autoFocus={!epilogueReady}
              onClick={requestClose}
              className="px-3.5 py-1.5 rounded-lg bg-white/10 hover:bg-white/15 text-gray-100 border border-fantasy-border text-xs font-semibold transition-colors"
            >
              {t('common.close', 'Close')}
            </button>
          )}
        </div>

        {/* Post-Chapter-11 Epilogue Actions (Archive vs. Endless Mode) */}
        {epilogueReady && onChooseEpilogue && (
          <div className="pt-3 border-t border-fantasy-border/60 space-y-2">
            <div className="flex items-center gap-1.5 text-[11px] text-amber-200 font-semibold">
              <Flame size={13} className="text-amber-400 shrink-0" />
              <span>{t('quests.choose_campaign_fate', 'Choose how this chronicle continues:')}</span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              <button
                type="button"
                disabled={Boolean(busyAction)}
                onClick={async () => {
                  await onChooseEpilogue('archive');
                  requestClose();
                }}
                className="py-2 px-3 rounded-lg bg-fantasy-accent/25 hover:bg-fantasy-accent/40 text-amber-200 border border-fantasy-accent/60 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
              >
                <Award size={14} />
                <span>{t('quests.epilogue_archive', 'Archive Campaign')}</span>
              </button>
              <button
                type="button"
                disabled={Boolean(busyAction)}
                onClick={async () => {
                  await onChooseEpilogue('endless');
                  requestClose();
                }}
                className="py-2 px-3 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/75 text-emerald-200 border border-emerald-600/60 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
              >
                <InfinityIcon size={14} />
                <span>
                  {isFallenWorld
                    ? t('quests.epilogue_resistance', 'Lead Fallen-World Resistance')
                    : t('quests.epilogue_endless', 'Continue in Endless World')}
                </span>
              </button>
            </div>
          </div>
        )}
      </div>
    </dialog>
  );
};

export default ChronicleTapestryModal;
