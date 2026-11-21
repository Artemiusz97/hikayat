import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useTranslation } from 'react-i18next';
import { Sparkles, RefreshCw, Maximize2, X } from 'lucide-react';
import { isTopEscapeLayer, registerEscapeLayer } from '../Common/MotionPrimitives';

export const SceneImageCard = ({
  imageUrl,
  title = 'Scene Illustration',
  isLatest = false,
  imageGenMode = 1, // 0 = disabled, 1 = auto, 2 = on_demand
  onReroll = null,
  isRerolling = false,
}) => {
  const { t } = useTranslation();
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const lightboxRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (!lightboxOpen) return undefined;

    const token = Symbol('scene-lightbox');
    const unregister = registerEscapeLayer(token);
    const prevOverflow = document.body.style.overflow;
    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    document.body.style.overflow = 'hidden';

    const frame = requestAnimationFrame(() => {
      const node = lightboxRef.current;
      if (node && !node.contains(document.activeElement)) {
        node.focus({ preventScroll: true });
      }
    });

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        setLightboxOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown, true);

    return () => {
      unregister();
      cancelAnimationFrame(frame);
      window.removeEventListener('keydown', handleKeyDown, true);
      document.body.style.overflow = prevOverflow;
      const prev = previousFocusRef.current;
      if (prev && typeof prev.focus === 'function' && prev.isConnected) {
        prev.focus({ preventScroll: true });
      }
    };
  }, [lightboxOpen]);

  // If there's no image and we are in On-Demand or Auto mode on the latest scene
  if (!imageUrl) {
    if (isLatest && (imageGenMode === 1 || String(imageGenMode).toLowerCase() === 'auto')) {
      return (
        <div className="mb-4 md:mb-5 px-3.5 py-2.5 rounded-xl border border-dashed border-fantasy-accent/40 bg-gray-500/10 flex items-center justify-between gap-3 animate-pulse">
          <div className="flex items-center gap-2.5 text-xs text-fantasy-accent font-serif">
            <Sparkles size={14} className="animate-spin text-fantasy-accent shrink-0" />
            <span>{t('feed.illustrating_background', 'Illustrating scene in background...')}</span>
          </div>
          <span className="text-[10px] font-mono text-gray-300 bg-gray-500/15 px-2 py-0.5 rounded uppercase tracking-wider">
            {t('feed.rendering', 'Rendering')}
          </span>
        </div>
      );
    }
    if (isLatest && (imageGenMode === 2 || String(imageGenMode).toLowerCase() === 'on_demand') && onReroll) {
      return (
        <div className="mb-4 md:mb-5 px-3.5 py-2.5 rounded-xl border border-dashed border-amber-500/40 bg-amber-500/10 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-amber-200/90 font-serif">
            <Sparkles size={14} className="text-amber-400 shrink-0" />
            <span>{t('feed.illustration_available', 'Scene illustration available on demand.')}</span>
          </div>
          <button
            type="button"
            onClick={onReroll}
            disabled={isRerolling}
            className="hk-btn hk-btn-ghost h-8 px-3 text-xs text-amber-200 hover:text-amber-100 shrink-0"
          >
            {isRerolling ? (
              <RefreshCw size={12} className="animate-spin text-amber-400" />
            ) : (
              <Sparkles size={12} className="text-amber-400" />
            )}
            <span>{isRerolling ? t('feed.illustrating', 'Illustrating...') : t('feed.illustrate_scene', 'Illustrate Scene')}</span>
          </button>
        </div>
      );
    }
    return null;
  }

  return (
    <>
      <div className="relative group mb-4 md:mb-5 rounded-xl overflow-hidden bg-black/25 flex items-center justify-center transition-all">
        {/* Responsive Centered Scene Illustration */}
        <img
          src={imageUrl}
          alt={title || 'Scene Illustration'}
          className="w-full max-h-[460px] sm:max-h-[560px] object-contain cursor-zoom-in transition-transform duration-300 group-hover:scale-[1.008]"
          onClick={() => setLightboxOpen(true)}
          loading="lazy"
        />

        {/* Floating Quick Actions Overlay */}
        <div className="hk-hover-reveal absolute top-2.5 right-2.5 flex items-center gap-1.5 z-10">
          {/* Zoom Lightbox Button */}
          <button
            type="button"
            onClick={() => setLightboxOpen(true)}
            className="p-1.5 rounded-lg bg-black/70 hover:bg-black/90 border border-white/20 text-gray-200 hover:text-white backdrop-blur-md shadow-lg transition-colors"
            title={t('feed.view_full_res', 'View full resolution')}
          >
            <Maximize2 size={13} />
          </button>

          {/* Reroll Button (Latest Scene only) */}
          {isLatest && imageGenMode !== 0 && onReroll && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onReroll();
              }}
              disabled={isRerolling}
              className="px-2.5 py-1 text-xs font-semibold rounded-lg bg-black/75 hover:bg-black/95 border border-amber-500/50 hover:border-amber-400 text-amber-300 backdrop-blur-md flex items-center gap-1.5 shadow-lg transition-all"
              title={t('feed.reroll_illustration', 'Reroll scene illustration')}
            >
              <RefreshCw size={12} className={isRerolling ? 'animate-spin text-amber-400' : 'text-amber-400'} />
              <span>{isRerolling ? t('feed.regenerating', 'Regenerating...') : t('feed.reroll', 'Reroll')}</span>
            </button>
          )}
        </div>
      </div>

      {/* Lightbox Modal (portaled to document.body to escape AcrylicPanel backdrop/transform clipping) */}
      {lightboxOpen &&
        typeof document !== 'undefined' &&
        createPortal(
          <div
            ref={lightboxRef}
            role="dialog"
            aria-modal="true"
            aria-label={title || t('feed.view_full_res', 'View full resolution')}
            tabIndex={-1}
            className="fixed inset-0 z-[70] flex items-center justify-center p-3 sm:p-6 bg-black/90 backdrop-blur-md animate-fadeIn outline-none"
            onClick={() => setLightboxOpen(false)}
          >
            <div className="relative max-w-5xl max-h-[calc(var(--app-height,100dvh)-1.5rem)] flex flex-col items-center">
              {/* Close Button */}
              <button
                type="button"
                onClick={() => setLightboxOpen(false)}
                aria-label={t('feed.close_preview', 'Close preview (Esc)')}
                className="absolute -top-10 right-0 sm:top-2 sm:right-2 p-2 rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/20 backdrop-blur-sm transition-colors z-20"
                title={t('feed.close_preview', 'Close preview (Esc)')}
              >
                <X size={20} />
              </button>

              {/* High-Res Image */}
              <img
                src={imageUrl}
                alt={title || 'Scene Illustration'}
                className="max-w-full max-h-[calc(var(--app-height,100dvh)-3rem)] object-contain rounded-lg shadow-2xl border border-fantasy-border/40 select-none"
                onClick={(e) => e.stopPropagation()}
              />

              {title && (
                <p className="mt-2 text-xs sm:text-sm font-rpg text-amber-300/90 text-center tracking-wide">
                  {title}
                </p>
              )}
            </div>
          </div>,
          document.body
        )}
    </>
  );
};

export default SceneImageCard;
