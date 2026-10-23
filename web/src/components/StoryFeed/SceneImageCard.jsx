import React, { useState, useEffect } from 'react';
import { Sparkles, RefreshCw, Maximize2, X } from 'lucide-react';

export const SceneImageCard = ({
  imageUrl,
  title = 'Scene Illustration',
  isLatest = false,
  imageGenMode = 1, // 0 = disabled, 1 = auto, 2 = on_demand
  onReroll = null,
  isRerolling = false,
}) => {
  const [lightboxOpen, setLightboxOpen] = useState(false);

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') setLightboxOpen(false);
    };
    if (lightboxOpen) {
      window.addEventListener('keydown', handleKeyDown);
      document.body.style.overflow = 'hidden';
    }
    return () => {
      window.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
    };
  }, [lightboxOpen]);

  // If there's no image and we are in On-Demand or Auto mode on the latest scene
  if (!imageUrl) {
    if (isLatest && (imageGenMode === 1 || String(imageGenMode).toLowerCase() === 'auto')) {
      return (
        <div className="mb-4 md:mb-5 p-3.5 rounded-xl border border-dashed border-fantasy-accent/40 bg-black/40 flex items-center justify-between gap-3 animate-pulse">
          <div className="flex items-center gap-2.5 text-xs text-fantasy-accent font-serif">
            <Sparkles size={14} className="animate-spin text-fantasy-accent shrink-0" />
            <span>Illustrating scene in background...</span>
          </div>
          <span className="text-[10px] font-mono text-gray-400 bg-white/5 px-2 py-0.5 rounded border border-white/10 uppercase tracking-wider">
            Rendering
          </span>
        </div>
      );
    }
    if (isLatest && (imageGenMode === 2 || String(imageGenMode).toLowerCase() === 'on_demand') && onReroll) {
      return (
        <div className="mb-4 md:mb-5 p-3 rounded-xl border border-dashed border-amber-500/40 bg-amber-950/10 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-amber-200/90 font-serif">
            <Sparkles size={14} className="text-amber-400 shrink-0" />
            <span>Scene illustration available on demand.</span>
          </div>
          <button
            type="button"
            onClick={onReroll}
            disabled={isRerolling}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-amber-600/20 hover:bg-amber-600/30 border border-amber-500/50 text-amber-200 flex items-center gap-1.5 transition-all shadow hover:shadow-amber-500/10 shrink-0"
          >
            {isRerolling ? (
              <RefreshCw size={12} className="animate-spin text-amber-400" />
            ) : (
              <Sparkles size={12} className="text-amber-400" />
            )}
            <span>{isRerolling ? 'Illustrating...' : 'Illustrate Scene'}</span>
          </button>
        </div>
      );
    }
    return null;
  }

  return (
    <>
      <div className="relative group mb-4 md:mb-5 rounded-xl overflow-hidden border border-fantasy-border/70 shadow-2xl bg-black/60 flex items-center justify-center transition-all">
        {/* Responsive Centered Scene Illustration */}
        <img
          src={imageUrl}
          alt={title || 'Scene Illustration'}
          className="w-full max-h-[500px] sm:max-h-[620px] object-contain cursor-zoom-in transition-transform duration-300 group-hover:scale-[1.008]"
          onClick={() => setLightboxOpen(true)}
          loading="lazy"
        />

        {/* Floating Quick Actions Overlay */}
        <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5 opacity-90 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity duration-200 z-10">
          {/* Zoom Lightbox Button */}
          <button
            type="button"
            onClick={() => setLightboxOpen(true)}
            className="p-1.5 rounded-lg bg-black/70 hover:bg-black/90 border border-white/20 text-gray-200 hover:text-white backdrop-blur-md shadow-lg transition-colors"
            title="View full resolution"
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
              title="Reroll scene illustration"
            >
              <RefreshCw size={12} className={isRerolling ? 'animate-spin text-amber-400' : 'text-amber-400'} />
              <span>{isRerolling ? 'Regenerating...' : 'Reroll'}</span>
            </button>
          )}
        </div>
      </div>

      {/* Lightbox Modal */}
      {lightboxOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-6 bg-black/90 backdrop-blur-md animate-fadeIn"
          onClick={() => setLightboxOpen(false)}
        >
          <div className="relative max-w-5xl max-h-[92vh] flex flex-col items-center">
            {/* Close Button */}
            <button
              type="button"
              onClick={() => setLightboxOpen(false)}
              className="absolute -top-10 right-0 sm:top-2 sm:right-2 p-2 rounded-full bg-black/60 hover:bg-black/80 text-white border border-white/20 backdrop-blur-sm transition-colors z-20"
              title="Close preview (Esc)"
            >
              <X size={20} />
            </button>

            {/* High-Res Image */}
            <img
              src={imageUrl}
              alt={title || 'Scene Illustration'}
              className="max-w-full max-h-[85vh] object-contain rounded-lg shadow-2xl border border-fantasy-border/40 select-none"
              onClick={(e) => e.stopPropagation()}
            />

            {title && (
              <p className="mt-2 text-xs sm:text-sm font-rpg text-amber-300/90 text-center tracking-wide">
                {title}
              </p>
            )}
          </div>
        </div>
      )}
    </>
  );
};

export default SceneImageCard;
