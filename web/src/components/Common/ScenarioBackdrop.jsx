import { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import {
  BACKGROUND_URLS,
  TIME_OF_DAY_GRADES,
  resolveScenarioBackdrop,
  resolveTimeOfDayPhase,
} from '../../theme/backgrounds';
import { useUiPreferences } from '../../theme/UiPreferencesProvider';

const CROSSFADE_EASE = [0.22, 1, 0.36, 1];

const ScenarioBackdrop = ({ session = null, isMenu = false }) => {
  const { ambientSceneBackdrop, illustratedBackdrops } = useUiPreferences();

  const backdropId = resolveScenarioBackdrop(isMenu ? null : session);
  const nextUrl = BACKGROUND_URLS[backdropId] || BACKGROUND_URLS.menu;

  const [layerState, setLayerState] = useState(() => ({
    currentUrl: nextUrl,
    previousUrl: null,
  }));
  const [failedUrls, setFailedUrls] = useState(() => new Set());

  useEffect(() => {
    setLayerState((prev) => {
      if (prev.currentUrl === nextUrl) return prev;
      return {
        currentUrl: nextUrl,
        previousUrl: prev.currentUrl,
      };
    });
  }, [nextUrl]);

  const markFailed = (url) => {
    if (!url) return;
    setFailedUrls((prev) => {
      if (prev.has(url)) return prev;
      const next = new Set(prev);
      next.add(url);
      return next;
    });
  };

  if (!illustratedBackdrops) {
    return (
      <div
        aria-hidden="true"
        className="hk-backdrop-root fixed inset-0 -z-10 pointer-events-none select-none overflow-hidden"
      >
        <div className="hk-pattern-backdrop absolute inset-0" />
      </div>
    );
  }

  const sceneImageUrl =
    !isMenu && ambientSceneBackdrop && session?.scene_image_url
      ? session.scene_image_url
      : null;

  const timePhase = isMenu
    ? 'neutral'
    : resolveTimeOfDayPhase(session?.formatted_time, session?.current_minute);
  const timeGrade = TIME_OF_DAY_GRADES[timePhase];

  const showPrevious =
    layerState.previousUrl &&
    layerState.previousUrl !== layerState.currentUrl &&
    !failedUrls.has(layerState.previousUrl);

  const showCurrent =
    layerState.currentUrl && !failedUrls.has(layerState.currentUrl);

  const showAmbientScene = sceneImageUrl && !failedUrls.has(sceneImageUrl);

  return (
    <div
      aria-hidden="true"
      className="hk-backdrop-root fixed inset-0 -z-10 pointer-events-none select-none overflow-hidden"
    >
      {showPrevious && (
        <img
          src={layerState.previousUrl}
          alt=""
          decoding="async"
          className="absolute inset-0 w-full h-full object-cover"
          onError={() => markFailed(layerState.previousUrl)}
        />
      )}

      {showCurrent && (
        <motion.img
          key={layerState.currentUrl}
          src={layerState.currentUrl}
          alt=""
          decoding="async"
          initial={showPrevious ? { opacity: 0 } : false}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.65, ease: CROSSFADE_EASE }}
          onAnimationComplete={() => {
            setLayerState((prev) =>
              prev.previousUrl
                ? { currentUrl: prev.currentUrl, previousUrl: null }
                : prev
            );
          }}
          onError={() => markFailed(layerState.currentUrl)}
          className="absolute inset-0 w-full h-full object-cover"
        />
      )}

      <AnimatePresence>
        {showAmbientScene && (
          <motion.img
            key={sceneImageUrl}
            src={sceneImageUrl}
            alt=""
            decoding="async"
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.72 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.75, ease: CROSSFADE_EASE }}
            onError={() => markFailed(sceneImageUrl)}
            className="absolute inset-0 w-full h-full object-cover scale-105 blur-[12px]"
          />
        )}
      </AnimatePresence>

      {timePhase !== 'neutral' && timeGrade !== 'none' && (
        <div
          className="absolute inset-0 transition-opacity duration-700"
          style={{ background: timeGrade }}
        />
      )}

      <div className="hk-backdrop-scrim absolute inset-0" />
    </div>
  );
};

export default ScenarioBackdrop;
