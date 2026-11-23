import { useState, useCallback, useRef } from 'react';
import { apiCall } from '../../api/client';

export const isAutoSceneImageGen = (s) =>
  s?.image_gen_enabled === true ||
  Number(s?.image_gen_enabled) === 1 ||
  String(s?.image_gen_enabled || '').trim().toLowerCase() === 'auto';

export const useSceneImagePoll = ({ session, user, setSession }) => {
  const imagePollIntervalRef = useRef(null);
  const imagePollAbortRef = useRef(null);
  const [rerollingImage, setRerollingImage] = useState(false);

  const clearImagePoll = useCallback(() => {
    if (imagePollIntervalRef.current) {
      clearInterval(imagePollIntervalRef.current);
      imagePollIntervalRef.current = null;
    }
    if (imagePollAbortRef.current) {
      try {
        imagePollAbortRef.current.abort();
      } catch {}
      imagePollAbortRef.current = null;
    }
  }, []);

  const pollForSceneImage = useCallback((sessionId, maxAttempts = 15) => {
    if (!sessionId) return;
    clearImagePoll();
    let attempts = 0;
    const interval = setInterval(async () => {
      attempts++;
      if (imagePollAbortRef.current) {
        try {
          imagePollAbortRef.current.abort();
        } catch {}
      }
      const controller = new AbortController();
      imagePollAbortRef.current = controller;
      try {
        const res = await apiCall(`/api/adventure/session-image/${sessionId}`, {
          signal: controller.signal,
        });
        if (imagePollIntervalRef.current !== interval || controller.signal.aborted) {
          return;
        }
        if (res && res.scene_image_url) {
          clearInterval(interval);
          if (imagePollIntervalRef.current === interval) {
            imagePollIntervalRef.current = null;
          }
          if (imagePollAbortRef.current === controller) {
            imagePollAbortRef.current = null;
          }
          setSession(prev => {
            if (!prev || (prev.id !== sessionId && String(prev.id) !== String(sessionId))) return prev;
            const hist = Array.isArray(prev.history) ? [...prev.history] : [];
            if (hist.length > 0 && typeof hist[hist.length - 1] === 'object') {
              hist[hist.length - 1] = {
                ...hist[hist.length - 1],
                scene_image_url: res.scene_image_url,
              };
            }
            return {
              ...prev,
              scene_image_url: res.scene_image_url,
              history: hist,
            };
          });
        } else if (attempts >= maxAttempts) {
          clearInterval(interval);
          if (imagePollIntervalRef.current === interval) {
            imagePollIntervalRef.current = null;
          }
          if (imagePollAbortRef.current === controller) {
            imagePollAbortRef.current = null;
          }
        }
      } catch (err) {
        if (err?.isUserAbort || err?.name === 'AbortError' || controller.signal.aborted) {
          return;
        }
        if (attempts >= maxAttempts) {
          clearInterval(interval);
          if (imagePollIntervalRef.current === interval) {
            imagePollIntervalRef.current = null;
          }
          if (imagePollAbortRef.current === controller) {
            imagePollAbortRef.current = null;
          }
        }
      }
    }, 2000);
    imagePollIntervalRef.current = interval;
  }, [clearImagePoll, setSession]);

  const rerollImage = async () => {
    if (!session?.id || !user?.user_id || rerollingImage) return null;
    setRerollingImage(true);
    try {
      const data = await apiCall('/api/adventure/reroll_image', {
        method: 'POST',
        body: JSON.stringify({
          session_id: session.id,
          user_id: user.user_id,
        }),
      });
      if (data?.image_url) {
        setSession(prev => {
          if (!prev) return prev;
          const hist = Array.isArray(prev.history) ? [...prev.history] : [];
          if (hist.length > 0 && typeof hist[hist.length - 1] === 'object') {
            hist[hist.length - 1] = {
              ...hist[hist.length - 1],
              scene_image_url: data.image_url,
            };
          }
          return {
            ...prev,
            scene_image_url: data.image_url,
            history: hist,
          };
        });
      }
      return data;
    } catch (err) {
      console.error('Reroll image failed:', err);
      throw err;
    } finally {
      setRerollingImage(false);
    }
  };

  return {
    clearImagePoll,
    pollForSceneImage,
    rerollImage,
    rerollingImage,
  };
};
