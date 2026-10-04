import React, { useState, useEffect, useCallback } from 'react';
import { X, Zap, BookOpen, Sliders, Check, ShieldAlert, Image as ImageIcon, Activity, RefreshCw, Terminal, HeartPulse, Skull } from 'lucide-react';
import { apiCall } from '../../api/client';

const SettingsModal = ({ isOpen, onClose, settingsHook, user, session, onSessionUpdated, onRefreshCharacter, onRefreshCodex }) => {
  const [activeTab, setActiveTab] = useState('preferences'); // 'preferences' | 'telemetry'
  const [telemetry, setTelemetry] = useState(null);
  const [debugStatMode, setDebugStatMode] = useState('off');
  const [debugCheckMode, setDebugCheckMode] = useState('off');
  const [debugRevealAll, setDebugRevealAll] = useState(0);
  const [loadingTelemetry, setLoadingTelemetry] = useState(false);
  const [debugNotice, setDebugNotice] = useState(null);

  const loadDiagnostics = useCallback(async () => {
    setLoadingTelemetry(true);
    try {
      if (user?.user_id) {
        const data = await apiCall(`/api/debug/${user.user_id}`);
        setTelemetry(data.telemetry || null);
        setDebugStatMode(data.debug_stat_mode || 'off');
        setDebugCheckMode(data.debug_check_mode || 'off');
        setDebugRevealAll(data.debug_reveal_all_info ? 1 : 0);
      } else {
        const data = await apiCall('/api/settings/debug/telemetry');
        setTelemetry(data.telemetry || null);
      }
    } catch {
      // ignore
    } finally {
      setLoadingTelemetry(false);
    }
  }, [user?.user_id]);

  useEffect(() => {
    if (isOpen && activeTab === 'telemetry') {
      loadDiagnostics();
    }
  }, [isOpen, activeTab, loadDiagnostics]);

  if (!isOpen) return null;

  const { settings, saving, updateSettings } = settingsHook;

  const handleToggleStreaming = () => {
    const currentVal = settings.stream_narrative ?? 1;
    updateSettings({ stream_narrative: currentVal === 1 ? 0 : 1 });
  };

  const handleToggleImageGen = () => {
    const currentVal = settings.image_gen_enabled ?? 0;
    updateSettings({ image_gen_enabled: currentVal === 1 ? 0 : 1 });
  };

  const handleVerbosityChange = (val) => {
    updateSettings({ verbosity: val });
  };

  const handleDialogueModeChange = (val) => {
    updateSettings({ dialogue_mode: val });
  };

  const handleResultDisplayChange = (val) => {
    updateSettings({ result_display: val });
  };

  const handleTogglePercentages = () => {
    const currentVal = settings.show_percentages ?? 1;
    updateSettings({ show_percentages: currentVal === 1 ? 0 : 1 });
  };

  const handleDebugUpdate = async (payload, label) => {
    if (!user?.user_id) return;
    try {
      const res = await apiCall(`/api/debug/${user.user_id}`, {
        method: 'POST',
        body: JSON.stringify(payload)
      });
      setDebugStatMode(res.debug_stat_mode || 'off');
      setDebugCheckMode(res.debug_check_mode || 'off');
      if (res.debug_reveal_all_info !== undefined) {
        setDebugRevealAll(res.debug_reveal_all_info ? 1 : 0);
      }
      setDebugNotice(label || 'Sandbox updated');
      if (payload.action && onRefreshCharacter) {
        onRefreshCharacter();
      }
      if (res.session && onSessionUpdated) {
        onSessionUpdated(res.session);
      }
      if ((payload.debug_reveal_all_info !== undefined || payload.action === 'reset_all') && onRefreshCodex) {
        onRefreshCodex();
      }
      setTimeout(() => setDebugNotice(null), 2500);
    } catch {
      // ignore
    }
  };

  const isStreamingOn = (settings.stream_narrative ?? 1) === 1;
  const isImageGenOn = (settings.image_gen_enabled ?? 0) === 1;
  const isShowPercentagesOn = (settings.show_percentages ?? 1) === 1;
  const circuitBreakers = Object.entries(telemetry?.circuit_breakers || {});

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fadeIn">
      <div 
        className="fixed inset-0" 
        onClick={onClose}
      />
      
      <div className="relative w-full max-w-lg bg-fantasy-panel border border-fantasy-border rounded-xl shadow-2xl overflow-hidden z-10">
        {/* Header */}
        <div className="flex items-center justify-between p-4 border-b border-fantasy-border bg-black/40">
          <div className="flex items-center gap-2">
            <Sliders className="text-fantasy-accent" size={18} />
            <h2 className="font-rpg font-bold text-lg text-gray-100">Chronicle Settings & Telemetry</h2>
          </div>
          <button 
            onClick={onClose} 
            className="p-1 rounded text-gray-400 hover:text-gray-200 hover:bg-white/5 transition-colors"
          >
            <X size={18} />
          </button>
        </div>

        {/* Sub-Navigation Tabs */}
        <div className="flex border-b border-fantasy-border bg-black/60 px-4 py-2 gap-2">
          <button
            onClick={() => setActiveTab('preferences')}
            className={`px-3 py-1 rounded text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors ${
              activeTab === 'preferences'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Sliders size={13} />
            <span>Preferences</span>
          </button>
          <button
            onClick={() => setActiveTab('telemetry')}
            className={`px-3 py-1 rounded text-xs font-semibold uppercase tracking-wider flex items-center gap-1.5 transition-colors ${
              activeTab === 'telemetry'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Activity size={13} />
            <span>Telemetry & Sandbox</span>
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-5 max-h-[75vh] overflow-y-auto custom-scrollbar">
          {activeTab === 'preferences' ? (
            <>
              {/* Section 1: Real-Time Narrative Streaming */}
              <div className="bg-black/30 border border-fantasy-border/60 rounded-lg p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <Zap size={16} className={isStreamingOn ? "text-amber-400" : "text-gray-500"} />
                      <span className="font-semibold text-gray-200 text-sm">Real-Time Narrative Streaming</span>
                      {isStreamingOn && (
                        <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          Live
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 leading-relaxed">
                      Stream the Chronicler&apos;s narrative token-by-token in real time over WebSockets as it is conceived.
                    </p>
                  </div>

                  {/* Toggle Switch */}
                  <button
                    type="button"
                    onClick={handleToggleStreaming}
                    disabled={saving}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      isStreamingOn ? 'bg-fantasy-accent' : 'bg-neutral-800 border border-neutral-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        isStreamingOn ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
                
                <div className="mt-3 pt-3 border-t border-white/5 flex items-center gap-2 text-[11px] text-gray-500">
                  <span className="w-1.5 h-1.5 rounded-full bg-gray-500" />
                  <span>{isStreamingOn ? "Tokens will flow smoothly in typewriter cadence." : "Batch mode: full scene is delivered all at once."}</span>
                </div>
              </div>

              {/* Section 1B: AI Scene Illustrations */}
              <div className="bg-black/30 border border-fantasy-border/60 rounded-lg p-4">
                <div className="flex items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <ImageIcon size={16} className={isImageGenOn ? "text-purple-400" : "text-gray-500"} />
                      <span className="font-semibold text-gray-200 text-sm">AI Scene Illustrations</span>
                      {isImageGenOn && (
                        <span className="text-[10px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-purple-500/20 text-purple-300 border border-purple-500/40">
                          Active
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 leading-relaxed">
                      Automatically generate and stream atmospheric artwork for new scenes in the background.
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={handleToggleImageGen}
                    disabled={saving}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      isImageGenOn ? 'bg-fantasy-accent' : 'bg-neutral-800 border border-neutral-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        isImageGenOn ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Section 2: Narrative Verbosity (5 Options) */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <BookOpen size={14} className="text-fantasy-accent" />
                  Story Verbosity
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    { id: 'shakespearean', label: '🎭 Shakespearean', desc: 'Ornate dramatic flourish' },
                    { id: 'vivid', label: '✨ Vivid', desc: 'Deep sensory prose' },
                    { id: 'normal', label: '⚖️ Balanced', desc: 'Standard narrative' },
                    { id: 'direct', label: '🎯 Direct', desc: 'Clear & brisk' },
                    { id: 'concise', label: '⚡ Concise', desc: 'Action-focused' }
                  ].map((v) => {
                    const isSelected = (settings.verbosity || 'normal') === v.id;
                    return (
                      <button
                        key={v.id}
                        onClick={() => handleVerbosityChange(v.id)}
                        className={`flex flex-col p-2.5 rounded-lg border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent shadow-sm'
                            : 'bg-black/30 border-fantasy-border text-gray-400 hover:border-neutral-600 hover:text-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1">
                          <span>{v.label}</span>
                          {isSelected && <Check size={12} />}
                        </div>
                        <span className="text-[10px] opacity-70 leading-tight">{v.desc}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Section 2B: NPC Dialogue Mode (5 Options) */}
              <div className="space-y-2">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Sliders size={14} className="text-fantasy-accent" />
                  NPC Dialogue Density
                </label>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                  {[
                    { id: 'off', label: '🔇 Off', desc: 'Pure narration only' },
                    { id: 'minimal', label: '💬 Minimal', desc: 'Brief spoken lines' },
                    { id: 'balanced', label: '⚖️ Balanced', desc: 'Natural conversation' },
                    { id: 'adaptive', label: '🧠 Adaptive', desc: 'Context-driven banter' },
                    { id: 'rich', label: '🎭 Rich', desc: 'Expressive character voice' },
                  ].map((d) => {
                    const isSelected = (settings.dialogue_mode || 'adaptive') === d.id;
                    return (
                      <button
                        key={d.id}
                        onClick={() => handleDialogueModeChange(d.id)}
                        className={`flex flex-col p-2.5 rounded-lg border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent shadow-sm'
                            : 'bg-black/30 border-fantasy-border text-gray-400 hover:border-neutral-600 hover:text-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1">
                          <span>{d.label}</span>
                          {isSelected && <Check size={12} />}
                        </div>
                        <span className="text-[10px] opacity-70 leading-tight">{d.desc}</span>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Section 3: Result Display & Show Percentages */}
              <div className="space-y-2.5">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <ShieldAlert size={14} className="text-fantasy-accent" />
                  Outcome Format & Odds
                </label>
                <div className="grid grid-cols-2 gap-2">
                  {[
                    { id: 'detailed', label: 'Detailed Breakdown', desc: 'Full stat breakdowns, modifiers & mechanics' },
                    { id: 'compact', label: 'Streamlined', desc: 'Clean summary badges only' }
                  ].map((r) => {
                    const isSelected = (settings.result_display || 'detailed') === r.id;
                    return (
                      <button
                        key={r.id}
                        onClick={() => handleResultDisplayChange(r.id)}
                        className={`flex flex-col p-2.5 rounded-lg border text-left transition-all ${
                          isSelected
                            ? 'bg-fantasy-accent/15 border-fantasy-accent text-fantasy-accent shadow-sm'
                            : 'bg-black/30 border-fantasy-border text-gray-400 hover:border-neutral-600 hover:text-gray-300'
                        }`}
                      >
                        <div className="flex items-center justify-between text-xs font-bold mb-1">
                          <span>{r.label}</span>
                          {isSelected && <Check size={12} />}
                        </div>
                        <span className="text-[10px] opacity-70 leading-tight">{r.desc}</span>
                      </button>
                    );
                  })}
                </div>

                <div className="flex items-center justify-between bg-black/30 border border-fantasy-border/60 rounded-lg p-3">
                  <div>
                    <span className="text-xs font-semibold text-gray-200 block">Show Skill Check Percentages</span>
                    <span className="text-[11px] text-gray-400">Display exact success chance (%) on action choices and check outcomes</span>
                  </div>
                  <button
                    type="button"
                    onClick={handleTogglePercentages}
                    disabled={saving}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      isShowPercentagesOn ? 'bg-fantasy-accent' : 'bg-neutral-800 border border-neutral-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        isShowPercentagesOn ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>

              {/* Section 4: Combat UI Toggles */}
              <div className="space-y-2.5">
                <label className="text-xs font-semibold text-gray-300 uppercase tracking-wider flex items-center gap-1.5">
                  <Activity size={14} className="text-fantasy-accent" />
                  Combat Interface
                </label>
                <div className="flex items-center justify-between bg-black/30 border border-fantasy-border/60 rounded-lg p-3">
                  <div>
                    <span className="text-xs font-semibold text-gray-200 block">Show Enemy Health Bars</span>
                    <span className="text-[11px] text-gray-400">Display exact HP values and visual bars for enemies</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => updateSettings({ show_enemy_hp: (settings.show_enemy_hp ?? 1) === 1 ? 0 : 1 })}
                    disabled={saving}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      (settings.show_enemy_hp ?? 1) === 1 ? 'bg-fantasy-accent' : 'bg-neutral-800 border border-neutral-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        (settings.show_enemy_hp ?? 1) === 1 ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
                <div className="flex items-center justify-between bg-black/30 border border-fantasy-border/60 rounded-lg p-3">
                  <div>
                    <span className="text-xs font-semibold text-gray-200 block">Show Combat Intent</span>
                    <span className="text-[11px] text-gray-400">Display what actions enemies are planning</span>
                  </div>
                  <button
                    type="button"
                    onClick={() => updateSettings({ show_enemy_intent: (settings.show_enemy_intent ?? 1) === 1 ? 0 : 1 })}
                    disabled={saving}
                    className={`relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                      (settings.show_enemy_intent ?? 1) === 1 ? 'bg-fantasy-accent' : 'bg-neutral-800 border border-neutral-700'
                    }`}
                  >
                    <span
                      className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                        (settings.show_enemy_intent ?? 1) === 1 ? 'translate-x-5' : 'translate-x-0'
                      }`}
                    />
                  </button>
                </div>
              </div>
            </>
          ) : (
            <div className="space-y-5">
              {/* Live LLM Telemetry & Circuit Breakers */}
              <div className="bg-black/30 border border-fantasy-border/70 rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-fantasy-accent flex items-center gap-1.5">
                    <Activity size={14} />
                    <span>LLM Gateway Telemetry & Circuit Breakers</span>
                  </h3>
                  <button
                    onClick={loadDiagnostics}
                    disabled={loadingTelemetry}
                    className="text-xs text-gray-400 hover:text-fantasy-accent flex items-center gap-1"
                  >
                    <RefreshCw size={12} className={loadingTelemetry ? 'animate-spin' : ''} />
                    <span>Refresh</span>
                  </button>
                </div>

                <div className="grid grid-cols-4 gap-2 text-center">
                  <div className="bg-black/50 border border-fantasy-border/60 rounded p-2">
                    <div className="text-[10px] text-gray-400 uppercase">Total Calls</div>
                    <div className="font-mono text-sm font-bold text-gray-100">{telemetry?.total_calls ?? 0}</div>
                  </div>
                  <div className="bg-black/50 border border-emerald-900/50 rounded p-2">
                    <div className="text-[10px] text-emerald-400 uppercase">Succeeded</div>
                    <div className="font-mono text-sm font-bold text-emerald-300">{telemetry?.successful_calls ?? 0}</div>
                  </div>
                  <div className="bg-black/50 border border-red-900/50 rounded p-2">
                    <div className="text-[10px] text-red-400 uppercase">Failed</div>
                    <div className="font-mono text-sm font-bold text-red-300">{telemetry?.failed_calls ?? 0}</div>
                  </div>
                  <div className="bg-black/50 border border-amber-900/50 rounded p-2">
                    <div className="text-[10px] text-amber-400 uppercase">Failovers</div>
                    <div className="font-mono text-sm font-bold text-amber-300">{telemetry?.fallback_activations ?? 0}</div>
                  </div>
                </div>

                <div className="space-y-1.5 pt-2 border-t border-fantasy-border/40">
                  <div className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">
                    Endpoint Circuit Breakers
                  </div>
                  {circuitBreakers.length === 0 ? (
                    <div className="text-xs text-emerald-400 font-mono bg-emerald-950/30 border border-emerald-800/40 rounded p-2">
                      🟢 All LLM endpoints healthy (Circuit CLOSED)
                    </div>
                  ) : (
                    circuitBreakers.map(([modelKey, cb]) => (
                      <div
                        key={modelKey}
                        className="flex items-center justify-between bg-black/50 border border-fantasy-border/60 rounded px-2.5 py-1.5 text-xs font-mono"
                      >
                        <span className="text-gray-300 truncate max-w-[240px]">{modelKey}</span>
                        {cb.is_open ? (
                          <span className="text-red-300 bg-red-950/70 border border-red-800 px-2 py-0.5 rounded text-[10px]">
                            🔴 OPEN ({cb.cooldown_remaining_s}s)
                          </span>
                        ) : (
                          <span className="text-emerald-300 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded text-[10px]">
                            🟢 CLOSED
                          </span>
                        )}
                      </div>
                    ))
                  )}
                </div>
              </div>

              {/* Developer Sandbox Controls */}
              {user?.user_id && (
                <div className="bg-black/30 border border-fantasy-border/70 rounded-lg p-4 space-y-3">
                  <div className="flex items-center justify-between">
                    <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5">
                      <Terminal size={14} />
                      <span>Developer Sandbox Overrides</span>
                    </h3>
                    {debugNotice && (
                      <span className="text-[10px] font-mono text-emerald-400">{debugNotice}</span>
                    )}
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-[10px] uppercase tracking-wider text-gray-400 mb-1">
                        Skill Check Override
                      </label>
                      <select
                        value={debugCheckMode}
                        onChange={(e) => handleDebugUpdate({ debug_check_mode: e.target.value }, 'Skill check mode updated')}
                        className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                      >
                        <option value="off">Normal (Standard Odds)</option>
                        <option value="always_success">Always Succeed (100%)</option>
                        <option value="always_fail">Always Fail (0%)</option>
                        <option value="always_crit_success">Force Critical Success</option>
                        <option value="always_crit_fail">Force Critical Failure</option>
                      </select>
                    </div>

                    <div>
                      <label className="block text-[10px] uppercase tracking-wider text-gray-400 mb-1">
                        Stat Override
                      </label>
                      <select
                        value={debugStatMode}
                        onChange={(e) => handleDebugUpdate({ debug_stat_mode: e.target.value }, 'Stat mode updated')}
                        className="w-full bg-fantasy-dark border border-fantasy-border p-2 rounded text-xs text-gray-100"
                      >
                        <option value="off">Normal Character Stats</option>
                        <option value="max">God Mode (All Stats 10)</option>
                        <option value="min">Weakened (All Stats 1)</option>
                      </select>
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-fantasy-border/40">
                    <button
                      type="button"
                      onClick={() => handleDebugUpdate({ action: 'full_heal' }, 'Character fully restored!')}
                      className="py-1.5 px-3 rounded bg-emerald-950/60 hover:bg-emerald-900/70 border border-emerald-700/60 text-emerald-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <HeartPulse size={13} />
                      <span>Full Heal HP/MP</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDebugUpdate({ action: 'hp_to_1' }, 'HP set to 1!')}
                      className="py-1.5 px-3 rounded bg-red-950/60 hover:bg-red-900/70 border border-red-800/60 text-red-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <Skull size={13} />
                      <span>Set HP to 1</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDebugUpdate({ debug_reveal_all_info: debugRevealAll ? 0 : 1 }, debugRevealAll ? 'NPC Info Lock Restored' : 'All NPC Info Revealed!')}
                      className={`py-1.5 px-3 rounded border text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors ${
                        debugRevealAll
                          ? 'bg-purple-900/70 border-purple-500 text-purple-200'
                          : 'bg-purple-950/50 hover:bg-purple-900/60 border-purple-700/60 text-purple-300'
                      }`}
                    >
                      <span>👁️ {debugRevealAll ? 'NPC Info: Revealed' : 'Reveal All NPC Info'}</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDebugUpdate({ action: 'force_enemy', session_id: session?.id }, 'Dummy enemy spawned!')}
                      className="py-1.5 px-3 rounded bg-amber-950/60 hover:bg-amber-900/70 border border-amber-700/60 text-amber-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <span>👹 Force Enemy (Spawn Dummy)</span>
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDebugUpdate({
                        action: 'reset_all',
                        debug_stat_mode: 'off',
                        debug_check_mode: 'off',
                        debug_reveal_all_info: 0
                      }, 'All sandbox overrides reset!')}
                      className="col-span-2 py-1.5 px-3 rounded bg-neutral-900 hover:bg-neutral-800 border border-neutral-700 text-gray-300 text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors"
                    >
                      <span>🔄 Reset All Overrides</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-fantasy-border bg-black/40 flex justify-end">
          <button
            onClick={onClose}
            className="px-4 py-1.5 bg-fantasy-accent hover:bg-fantasy-accent/90 text-fantasy-dark font-bold text-xs uppercase tracking-wider rounded transition-colors"
          >
            Done
          </button>
        </div>
      </div>
    </div>
  );
};

export default SettingsModal;
