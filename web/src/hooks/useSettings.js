import { useState, useEffect, useCallback, useRef } from 'react';
import { apiCall } from '../api/client';
import i18n from '../i18n';

export const useSettings = (userId) => {
  const [settings, setSettings] = useState({
    stream_narrative: 1,
    verbosity: 'vivid',
    narrative_pacing: 'balanced',
    dialogue_mode: 'adaptive',
    result_display: 'detailed',
    choices_style: 'dropdown',
    show_percentages: 1,
    show_enemy_hp: 1,
    show_enemy_intent: 1,
    image_gen_enabled: 0,
    language: 'en'
  });
  const settingsRef = useRef(settings);
  settingsRef.current = settings;
  const fetchAbortRef = useRef(null);
  const fetchSeqRef = useRef(0);
  const updateSeqRef = useRef(0);
  const savingCountRef = useRef(0);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const fetchSettings = useCallback(async () => {
    if (fetchAbortRef.current) {
      try {
        fetchAbortRef.current.abort();
      } catch {}
      fetchAbortRef.current = null;
    }
    const seq = ++fetchSeqRef.current;
    if (!userId) {
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    fetchAbortRef.current = controller;
    try {
      setLoading(true);
      const data = await apiCall(`/api/settings/${userId}`, {
        signal: controller.signal,
      });
      if (controller.signal.aborted || fetchSeqRef.current !== seq) {
        return;
      }
      if (data && data.settings) {
        settingsRef.current = data.settings;
        setSettings(data.settings);
        const uiLang = data.settings.ui_language || localStorage.getItem('hikayat_ui_language') || data.settings.language;
        if (uiLang && uiLang !== i18n.language) {
          i18n.changeLanguage(uiLang);
          localStorage.setItem('hikayat_ui_language', uiLang);
        }
      }
    } catch (err) {
      if (err?.isUserAbort || err?.name === 'AbortError' || controller.signal.aborted || fetchSeqRef.current !== seq) {
        return;
      }
      console.error('Failed to fetch settings:', err);
      setError(err.message || 'Could not load settings');
    } finally {
      if (fetchAbortRef.current === controller) {
        fetchAbortRef.current = null;
      }
      if (fetchSeqRef.current === seq) {
        setLoading(false);
      }
    }
  }, [userId]);

  useEffect(() => {
    fetchSettings();
    return () => {
      if (fetchAbortRef.current) {
        try {
          fetchAbortRef.current.abort();
        } catch {}
        fetchAbortRef.current = null;
      }
    };
  }, [fetchSettings]);

  const updateSettings = async (newFields) => {
    if (!userId) return;
    if (fetchAbortRef.current) {
      try {
        fetchAbortRef.current.abort();
      } catch {}
      fetchAbortRef.current = null;
    }
    fetchSeqRef.current += 1;
    const seq = ++updateSeqRef.current;
    savingCountRef.current += 1;
    try {
      setSaving(true);
      setError(null);
      const merged = { ...settingsRef.current, ...newFields, user_id: userId };
      if (
        newFields?.narrative_pacing &&
        ['concise', 'direct'].includes(String(merged.verbosity || '').toLowerCase())
      ) {
        merged.verbosity = 'normal';
      }
      settingsRef.current = merged;
      // Optimistic update
      setSettings(prev => {
        const next = { ...prev, ...newFields, user_id: userId };
        if (
          newFields?.narrative_pacing &&
          ['concise', 'direct'].includes(String(next.verbosity || '').toLowerCase())
        ) {
          next.verbosity = 'normal';
        }
        return next;
      });

      const res = await apiCall(`/api/settings/${userId}`, {
        method: 'POST',
        body: JSON.stringify(merged)
      });
      if (res && res.settings && seq === updateSeqRef.current) {
        settingsRef.current = res.settings;
        setSettings(res.settings);
      }
      return res;
    } catch (err) {
      console.error('Failed to save settings:', err);
      if (seq === updateSeqRef.current) {
        setError(err.message || 'Could not save settings');
        // Re-fetch on error to revert
        fetchSettings();
      }
      throw err;
    } finally {
      savingCountRef.current = Math.max(0, savingCountRef.current - 1);
      if (savingCountRef.current === 0) {
        setSaving(false);
      }
    }
  };

  return {
    settings,
    loading,
    saving,
    error,
    updateSettings
  };
};
