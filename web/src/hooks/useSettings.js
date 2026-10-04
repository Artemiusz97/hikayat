import { useState, useEffect, useCallback } from 'react';
import { apiCall } from '../api/client';

export const useSettings = (userId) => {
  const [settings, setSettings] = useState({
    stream_narrative: 1,
    verbosity: 'vivid',
    dialogue_mode: 'balanced',
    result_display: 'detailed',
    choices_style: 'dropdown',
    show_percentages: 1,
    image_gen_enabled: 0
  });
  const [debugState, setDebugState] = useState({
    debug_stat_mode: 'off',
    debug_check_mode: 'off',
    debug_reveal_all_info: 0,
    telemetry: null
  });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState(null);

  const fetchSettings = useCallback(async () => {
    if (!userId) return;
    try {
      setLoading(true);
      const data = await apiCall(`/api/settings/${userId}`);
      if (data && data.settings) {
        setSettings(data.settings);
      }
      try {
        const dbg = await apiCall(`/api/debug/${userId}`);
        if (dbg) {
          setDebugState({
            debug_stat_mode: dbg.debug_stat_mode || 'off',
            debug_check_mode: dbg.debug_check_mode || 'off',
            debug_reveal_all_info: dbg.debug_reveal_all_info ?? 0,
            telemetry: dbg.telemetry || null
          });
        }
      } catch {
        // ignore debug fetch errors
      }
    } catch (err) {
      console.error('Failed to fetch settings:', err);
      setError(err.message || 'Could not load settings');
    } finally {
      setLoading(false);
    }
  }, [userId]);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const updateSettings = async (newFields) => {
    if (!userId) return;
    try {
      setSaving(true);
      const merged = { ...settings, ...newFields, user_id: userId };
      // Optimistic update
      setSettings(merged);

      const res = await apiCall(`/api/settings/${userId}`, {
        method: 'POST',
        body: JSON.stringify(merged)
      });
      if (res && res.settings) {
        setSettings(res.settings);
      }
      return res;
    } catch (err) {
      console.error('Failed to save settings:', err);
      setError(err.message || 'Could not save settings');
      // Re-fetch on error to revert
      fetchSettings();
      throw err;
    } finally {
      setSaving(false);
    }
  };

  const updateDebug = async ({ debug_stat_mode, debug_check_mode, debug_reveal_all_info, action, session_id } = {}) => {
    if (!userId) return null;
    const res = await apiCall(`/api/debug/${userId}`, {
      method: 'POST',
      body: JSON.stringify({
        debug_stat_mode,
        debug_check_mode,
        debug_reveal_all_info,
        action,
        session_id
      })
    });
    if (res) {
      setDebugState(prev => ({
        ...prev,
        debug_stat_mode: res.debug_stat_mode ?? prev.debug_stat_mode,
        debug_check_mode: res.debug_check_mode ?? prev.debug_check_mode,
        debug_reveal_all_info: res.debug_reveal_all_info ?? prev.debug_reveal_all_info,
        telemetry: res.telemetry ?? prev.telemetry
      }));
    }
    return res;
  };

  return {
    settings,
    debugState,
    loading,
    saving,
    error,
    updateSettings,
    updateDebug,
    refreshSettings: fetchSettings
  };
};
