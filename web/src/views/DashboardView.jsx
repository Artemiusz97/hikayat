import React, { useState, useEffect, useCallback } from 'react';
import { LogOut, Play, Users, Sword, Sliders, RefreshCw, Sparkles, Trash2, Plus, LogIn, Compass, Globe } from 'lucide-react';
import SettingsModal from '../components/Settings/SettingsModal';
import CharacterCreatorModal from '../components/Character/CharacterCreatorModal';
import EmbarkationModal from '../components/Adventure/EmbarkationModal';
import { apiCall } from '../api/client';
import { useTranslation } from 'react-i18next';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
import ThemeSwitcher from '../components/Common/ThemeSwitcher';
import { useSettings } from '../hooks/useSettings';

const DashboardView = ({
  user,
  character,
  characters,
  logout,
  createCharacter,
  switchCharacter,
  deleteCharacter,
  startSession,
  joinSession,
  activeSession,
  onResumeSession,
  onResumeSlot,
  onEndSession,
  onEndSlot,
  refreshCharacter,
  refreshSession,
  onSessionLoaded
}) => {
  const { t } = useTranslation();
  const [creatorOpen, setCreatorOpen] = useState(false);
  const [embarkOpen, setEmbarkOpen] = useState(false);
  
  const [settingsModalOpen, setSettingsModalOpen] = useState(false);
  const [scenarios, setScenarios] = useState([]);
  const [availableTags, setAvailableTags] = useState([]);
  
  const [saves, setSaves] = useState([]);
  const [loadingSaves, setLoadingSaves] = useState(false);
  const [selectedSlot, setSelectedSlot] = useState(1);
  const [characterSessions, setCharacterSessions] = useState([]);
  const [loadingSessions, setLoadingSessions] = useState(false);
  
  const [lobbies, setLobbies] = useState([]);
  const [loadingLobbies, setLoadingLobbies] = useState(false);
  const [joinCode, setJoinCode] = useState('');

  const [mobileTab, setMobileTab] = useState(() => {
    return (characters && characters.length === 0) ? 'characters' : 'adventures';
  });

  useEffect(() => {
    if (characters && characters.length === 0) {
      setMobileTab('characters');
    }
  }, [characters?.length]);

  const settings = useSettings(user?.user_id);

  const fetchLobbies = useCallback(() => {
    setLoadingLobbies(true);
    apiCall('/api/adventure/lobbies')
      .then(data => setLobbies(data.lobbies || []))
      .catch(() => {})
      .finally(() => setLoadingLobbies(false));
  }, []);

  const fetchSaves = useCallback(() => {
    if (!user?.user_id || !character?.id) return;
    setLoadingSaves(true);
    apiCall(`/api/saves/${user.user_id}`)
      .then(data => setSaves(data.saves || []))
      .catch(() => {})
      .finally(() => setLoadingSaves(false));
  }, [user?.user_id, character?.id]);

  const fetchCharacterSessions = useCallback(() => {
    if (!character?.id) {
      setCharacterSessions([]);
      return;
    }
    setLoadingSessions(true);
    apiCall(`/api/adventure/character-sessions/${character.id}`)
      .then(data => {
        setCharacterSessions(data.sessions || []);
      })
      .catch(err => {
        console.error("Failed to fetch character sessions:", err);
      })
      .finally(() => {
        setLoadingSessions(false);
      });
  }, [character?.id]);

  useEffect(() => {
    apiCall('/api/scenarios')
      .then(data => {
        const list = data.scenario_list || (Array.isArray(data.scenarios) ? data.scenarios : []);
        if (list.length > 0) setScenarios(list);
      })
      .catch(() => {});
      
    apiCall('/api/genres')
      .then(data => {
        const list = data.genre_list || data.tag_list || (Array.isArray(data.genres) ? data.genres : Object.entries(data.genres || {}).map(([key, val]) => ({ key, ...val })));
        if (list.length > 0) setAvailableTags(list);
      })
      .catch(() => {});
      
    fetchLobbies();
  }, [fetchLobbies]);

  useEffect(() => {
    fetchSaves();
    fetchCharacterSessions();
    if (refreshSession) {
      refreshSession();
    }
  }, [fetchSaves, fetchCharacterSessions, refreshSession, character?.id]); // re-fetch when character changes

  const handleEmbark = async (config) => {
    await startSession(config.scenario, config.mode, {
       tags: config.tags,
       capacity: 4,
       slot: config.slot || selectedSlot || 1,
       character_id: character?.id,
       ...config
    });
    if (refreshCharacter) {
      await refreshCharacter();
    }
    fetchCharacterSessions();
  };

  const handleLoadSave = async (slotName) => {
    try {
       const res = await apiCall('/api/saves/load', {
         method: 'POST',
         body: JSON.stringify({ user_id: user.user_id, slot_name: slotName })
       });
       if (res.loaded) {
          if (onSessionLoaded) onSessionLoaded(res.loaded);
       }
    } catch (e) {
       console.error("Failed to load save", e);
    }
  };

  const handleDeleteSave = async (slotName, e) => {
    e.stopPropagation();
    if (!window.confirm(`Delete checkpoint "${slotName}"?`)) return;
    try {
      await apiCall(`/api/saves/${user.user_id}/${encodeURIComponent(slotName)}`, { method: 'DELETE' });
      fetchSaves();
    } catch (err) {
      console.error("Failed to delete save", err);
    }
  };

  const handleResume = (sess) => {
    if (onResumeSlot) {
      onResumeSlot(sess);
    } else if (onResumeSession) {
      onResumeSession();
    }
  };

  const handleEnd = async (sessId, e) => {
    if (e) e.stopPropagation();
    if (!window.confirm(t("dashboard.confirm_end_session", "End this adventure session?"))) return;
    if (onEndSlot) {
      await onEndSlot(sessId);
    } else if (onEndSession) {
      await onEndSession();
    }
    fetchCharacterSessions();
  };

  const slots = Array.from({ length: 6 }, (_, idx) => {
    const slotNum = idx + 1;
    let found = (characterSessions || []).find(s => Number(s.slot) === slotNum);
    if (!found && activeSession && (Number(activeSession.slot) === slotNum || (slotNum === 1 && !characterSessions.some(s => s.id === activeSession.id)))) {
      found = activeSession;
    }
    if (found) {
      return { type: 'active', data: found, slotNum };
    }
    return { type: 'empty', slotNum };
  });

  const unassigned = (characterSessions || []).filter(s => !s.slot || s.slot < 1 || s.slot > 6);
  if (unassigned.length > 0) {
    let uIdx = 0;
    for (let i = 0; i < slots.length && uIdx < unassigned.length; i++) {
      if (slots[i].type === 'empty') {
        slots[i] = { type: 'active', data: unassigned[uIdx], slotNum: i + 1 };
        uIdx++;
      }
    }
  }

  const activeSlots = slots.filter((s) => s.type === 'active');
  const emptySlots = slots.filter((s) => s.type === 'empty');
  const statPreview = character ? [
    { label: 'STR', val: character.str_ ?? character.str ?? 1 },
    { label: 'PER', val: character.per_ ?? character.per ?? 1 },
    { label: 'END', val: character.end_ ?? character.end ?? 1 },
    { label: 'CHA', val: character.cha ?? 1 },
    { label: 'INT', val: character.int_ ?? character.int ?? 1 },
    { label: 'AGI', val: character.agi ?? 1 },
    { label: 'LUK', val: character.luk ?? 1 },
  ] : [];

  const selectCharacter = async (c, goToAdventures = false) => {
    await switchCharacter(c.id);
    if (refreshSession) refreshSession();
    if (goToAdventures) setMobileTab('adventures');
  };

  const mobileTabs = [
    { id: 'adventures', icon: Compass, label: t('dashboard.adventures', 'Adventures'), dot: Boolean(activeSession || character?.active_session_id) },
    { id: 'characters', icon: Users, label: t('dashboard.characters', 'Characters'), count: characters.length },
    { id: 'lobbies', icon: Globe, label: t('dashboard.lobbies', 'Lobbies'), count: lobbies.length || null },
  ];

  return (
    <div className="h-full min-h-0 overflow-y-auto text-gray-100 flex flex-col font-sans custom-scrollbar">
      {/* Header */}
      <header className="sticky top-0 z-20 shrink-0 border-b border-fantasy-border/50 bg-fantasy-dark/70 backdrop-blur-xl">
        <div className="max-w-6xl mx-auto px-3 sm:px-6 h-14 sm:h-16 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="grid place-items-center w-9 h-9 rounded-xl bg-fantasy-accent text-black shadow-md shrink-0">
              <Sword size={18} />
            </div>
            <div className="min-w-0 leading-tight">
              <h1 className="hk-display font-bold text-base sm:text-lg text-gray-50 truncate">Hikayat</h1>
              <span className="hidden sm:block text-[11px] text-gray-500 truncate">{t('dashboard.chronicles_console', 'Chronicles Console')}</span>
            </div>
          </div>
          <div className="flex items-center gap-0.5 sm:gap-1 shrink-0">
            <span className="hidden sm:inline-flex hk-chip mr-1 max-w-[160px] truncate">
              {user?.display_name || user?.username || t('dashboard.guest', 'Guest')}
            </span>
            <ThemeSwitcher />
            <LanguageSwitcher settingsHook={settings} />
            <button onClick={() => setSettingsModalOpen(true)} className="hk-icon-btn" title={t('nav.settings')} aria-label={t('nav.settings')}>
              <Sliders size={16} />
            </button>
            <button onClick={logout} className="hk-icon-btn is-danger" title={t('dashboard.logout')} aria-label={t('dashboard.logout')}>
              <LogOut size={16} />
            </button>
          </div>
        </div>
      </header>

      <main className="flex-1 w-full max-w-6xl mx-auto px-3 sm:px-6 pt-4 sm:pt-8 pb-28 sm:pb-10 grid grid-cols-1 lg:grid-cols-12 content-start items-start gap-4 lg:gap-8">
        {/* Mobile segmented navigation */}
        <div className="lg:hidden sticky top-14 z-10 -mx-3 px-3 pb-3 pt-1 bg-gradient-to-b from-fantasy-darker via-fantasy-darker/90 to-transparent">
          <div className="hk-segmented" role="tablist">
            {mobileTabs.map(({ id, icon: Icon, label, dot, count }) => (
              <button key={id} type="button" role="tab" aria-selected={mobileTab === id} onClick={() => setMobileTab(id)}>
                <Icon size={14} />
                <span className="truncate">{label}</span>
                {dot && <span className="w-1.5 h-1.5 rounded-full bg-fantasy-accent" />}
                {count ? <span className="text-[10px] text-gray-500 tabular-nums">{count}</span> : null}
              </button>
            ))}
          </div>
        </div>

        {/* Left rail: roster & lobbies */}
        <aside className={`lg:col-span-4 space-y-4 lg:space-y-6 ${mobileTab === 'characters' || mobileTab === 'lobbies' ? 'block' : 'hidden lg:block'}`}>
          <section className={`hk-surface p-4 sm:p-5 ${mobileTab === 'characters' ? 'block' : 'hidden lg:block'}`}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="hk-section-title"><Users size={15} className="text-fantasy-accent" /> {t('dashboard.characters')}</h2>
              <span className="text-xs text-gray-500 tabular-nums">{characters.length} / 6</span>
            </div>

            <ul className="space-y-1.5">
              {characters.map((c, i) => {
                const isActive = character?.id === c.id;
                const hasActiveSession = Boolean(c.active_session_id);
                return (
                  <li key={c.id} className="hk-enter" style={{ '--i': i }}>
                    <div
                      role="button"
                      tabIndex={0}
                      onClick={() => selectCharacter(c, true)}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); selectCharacter(c, true); } }}
                      className={`group flex items-center gap-3 rounded-xl px-2.5 py-2 cursor-pointer border ${
                        isActive ? 'bg-fantasy-accent/10 border-fantasy-accent/40' : 'border-transparent hover:bg-gray-500/10'
                      }`}
                    >
                      <span className={`grid place-items-center w-9 h-9 rounded-full text-sm font-bold shrink-0 ${isActive ? 'bg-fantasy-accent text-black' : 'bg-gray-500/15 text-gray-300'}`}>
                        {(c.name || '?').charAt(0).toUpperCase()}
                      </span>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className="font-semibold text-sm text-gray-100 truncate">{c.name}</span>
                          {hasActiveSession && <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 shrink-0" title={t('dashboard.in_adventure', 'In Adventure')} />}
                        </div>
                        <div className="text-xs text-gray-500 truncate">
                          {t('dashboard.level_short', 'Lv')} {c.level} · {c.char_class}{c.race ? ` · ${c.race}` : ''}
                        </div>
                      </div>
                      {hasActiveSession && (
                        <button
                          type="button"
                          onClick={async (e) => {
                            e.stopPropagation();
                            if (!isActive) await selectCharacter(c);
                            onResumeSession();
                          }}
                          className="lg:hidden hk-btn hk-btn-primary h-8 px-3 text-xs"
                          title={t('dashboard.resume', 'Resume')}
                        >
                          <Play size={11} className="fill-current" />
                          {t('dashboard.resume', 'Resume')}
                        </button>
                      )}
                      <button
                        onClick={(e) => { e.stopPropagation(); deleteCharacter(c.id); }}
                        className="hk-icon-btn is-danger h-8 min-w-8 opacity-60 lg:opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
                        title={t('common.delete', 'Delete')}
                        aria-label={t('common.delete', 'Delete')}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>

            {characters.length < 6 && (
              <button
                onClick={() => setCreatorOpen(true)}
                className="mt-3 w-full hk-btn hk-btn-ghost border border-dashed border-fantasy-border/80 hover:border-fantasy-accent/60 hover:text-fantasy-accent"
              >
                <Plus size={15} /> {t('dashboard.create_character', 'Create Character')}
              </button>
            )}
          </section>

          <section className={`hk-surface p-4 sm:p-5 ${mobileTab === 'lobbies' ? 'block' : 'hidden lg:block'}`}>
            <div className="flex items-center justify-between mb-3">
              <h2 className="hk-section-title"><Globe size={15} className="text-fantasy-accent" /> {t('dashboard.lobbies', 'Lobbies')}</h2>
              <button onClick={fetchLobbies} className="hk-icon-btn h-8 min-w-8" title={t('common.refresh', 'Refresh')} aria-label={t('common.refresh', 'Refresh')}>
                <RefreshCw size={14} className={loadingLobbies ? 'animate-spin' : ''} />
              </button>
            </div>

            <div className="space-y-1.5 max-h-56 overflow-y-auto custom-scrollbar -mx-1 px-1">
              {lobbies.length === 0 ? (
                <div className="text-xs text-gray-500 text-center py-6">{t('dashboard.no_lobbies', 'No active lobbies')}</div>
              ) : (
                lobbies.map((l, i) => (
                  <div key={l.id} className="hk-enter flex items-center justify-between gap-2 rounded-xl px-2.5 py-2 hover:bg-gray-500/10" style={{ '--i': i }}>
                    <div className="min-w-0">
                      <div className="text-sm font-medium text-gray-200 truncate">{l.scene_title}</div>
                      <div className="text-[11px] text-gray-500 truncate">{l.host_name}</div>
                    </div>
                    <button onClick={() => joinSession(l.id)} className="hk-btn hk-btn-ghost h-8 px-3 text-xs shrink-0">{t('dashboard.join', 'Join')}</button>
                  </div>
                ))
              )}
            </div>

            <form
              className="mt-3 pt-3 border-t border-fantasy-border/50 flex gap-2"
              onSubmit={(e) => { e.preventDefault(); if (joinCode.trim()) joinSession(joinCode.trim()); }}
            >
              <input
                type="text"
                placeholder={t('dashboard.invite_code_placeholder', 'Invite Code...')}
                value={joinCode}
                onChange={(e) => setJoinCode(e.target.value)}
                className="hk-input h-9 text-xs"
              />
              <button type="submit" disabled={!joinCode.trim()} className="hk-btn hk-btn-ghost h-9 px-3 text-xs shrink-0">
                <LogIn size={14} /> {t('dashboard.join', 'Join')}
              </button>
            </form>
          </section>
        </aside>

        {/* Main column: hero + adventures */}
        <section className={`lg:col-span-8 space-y-4 sm:space-y-6 ${mobileTab === 'adventures' ? 'block' : 'hidden lg:block'}`}>
          {/* Mobile quick character switcher */}
          {characters.length > 0 && (
            <div className="lg:hidden flex items-center gap-1.5 overflow-x-auto no-scrollbar -mx-3 px-3">
              {characters.map((c) => {
                const isSelected = character?.id === c.id;
                return (
                  <button
                    key={c.id}
                    type="button"
                    onClick={() => selectCharacter(c)}
                    className={`shrink-0 h-8 px-3 rounded-full text-xs font-semibold flex items-center gap-1.5 border ${
                      isSelected ? 'bg-fantasy-accent text-black border-transparent' : 'border-fantasy-border/70 text-gray-400 hover:text-gray-200'
                    }`}
                  >
                    {c.name}
                    {c.active_session_id && <span className={`w-1.5 h-1.5 rounded-full ${isSelected ? 'bg-black' : 'bg-emerald-400'}`} />}
                  </button>
                );
              })}
              {characters.length < 6 && (
                <button type="button" onClick={() => setCreatorOpen(true)} className="shrink-0 h-8 px-3 rounded-full border border-dashed border-fantasy-border text-gray-400 text-xs flex items-center gap-1">
                  <Plus size={12} /> {t('common.new', 'New')}
                </button>
              )}
            </div>
          )}

          {!character ? (
            <div className="hk-surface flex flex-col items-center justify-center text-center py-20 px-6 hk-enter">
              <div className="grid place-items-center w-16 h-16 rounded-2xl bg-fantasy-accent/10 text-fantasy-accent mb-5">
                <Sparkles size={28} />
              </div>
              <h2 className="hk-display text-xl font-bold text-gray-100">{t('dashboard.welcome_title', 'Begin your chronicle')}</h2>
              <p className="text-sm text-gray-400 mt-2 max-w-sm">{t('dashboard.no_character_selected', 'Select or create a character to view adventures.')}</p>
              <button type="button" onClick={() => setCreatorOpen(true)} className="hk-btn hk-btn-primary mt-6">
                <Plus size={15} /> {t('dashboard.create_character', 'Create Character')}
              </button>
            </div>
          ) : (
            <>
              {/* Hero summary */}
              <div className="hk-surface p-5 sm:p-6 hk-enter">
                <div className="flex items-start justify-between gap-4">
                  <div className="min-w-0">
                    <p className="text-xs text-gray-500">{t('dashboard.select_hero', 'Active Character')}</p>
                    <h2 className="hk-display text-2xl sm:text-3xl font-bold text-gray-50 truncate mt-0.5">{character.name}</h2>
                    <div className="flex flex-wrap items-center gap-1.5 mt-2">
                      <span className="hk-chip hk-chip-accent">{t('dashboard.level_short', 'Lv')} {character.level}</span>
                      {character.char_class && <span className="hk-chip">{character.char_class}</span>}
                      {character.race && <span className="hk-chip">{character.race}</span>}
                      {character.gender && <span className="hk-chip">{character.gender}</span>}
                    </div>
                  </div>
                  <Compass size={40} className="text-fantasy-accent/30 shrink-0 hidden sm:block" />
                </div>
                <div className="mt-5 grid grid-cols-7 gap-1.5 sm:gap-2">
                  {statPreview.map((st) => (
                    <div key={st.label} className="rounded-xl bg-gray-500/10 py-2 text-center" title={`${st.label}: ${st.val}`}>
                      <div className="text-[10px] font-medium text-gray-500">{st.label}</div>
                      <div className="text-base font-bold text-gray-100 tabular-nums">{st.val}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Adventures */}
              <div>
                <div className="flex items-end justify-between mb-3 px-1">
                  <div>
                    <h3 className="hk-section-title text-base"><Compass size={16} className="text-fantasy-accent" /> {t('dashboard.adventures', 'Adventures')}</h3>
                    <p className="text-xs text-gray-500 mt-0.5">{t('dashboard.adventures_subtitle', 'Manage active sessions and checkpoints, or embark on a new journey.')}</p>
                  </div>
                  <span className="text-xs text-gray-500 tabular-nums">{activeSlots.length} / 6</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  {activeSlots.map((slot, i) => (
                    <article key={`active-${slot.slotNum}`} className="hk-card hk-card-interactive hk-enter p-4 flex flex-col border-fantasy-accent/40" style={{ '--i': i }}>
                      <div className="flex items-center justify-between mb-2">
                        <span className="hk-chip hk-chip-accent">
                          <span className="w-1.5 h-1.5 rounded-full bg-fantasy-accent animate-pulse" />
                          {t('dashboard.live', 'Live')}
                        </span>
                        <span className="text-[11px] text-gray-500 tabular-nums">#{slot.slotNum}</span>
                      </div>
                      <h4 className="font-semibold text-gray-100 leading-snug line-clamp-1">{slot.data.scene_title || slot.data.scenario_display_name || slot.data.scenario}</h4>
                      <p className="text-xs text-gray-400 mt-1 line-clamp-2 flex-1">{slot.data.narrative_snippet || t('dashboard.journey_continues', 'Journey continues...')}</p>
                      <div className="mt-4 flex gap-2">
                        <button onClick={() => handleResume(slot.data)} className="hk-btn hk-btn-primary flex-1">
                          <Play size={13} className="fill-current" /> {t('dashboard.resume', 'Resume')}
                        </button>
                        <button onClick={(e) => handleEnd(slot.data.id, e)} className="hk-btn hk-btn-ghost px-3">
                          {t('dashboard.end', 'End')}
                        </button>
                      </div>
                    </article>
                  ))}

                  {emptySlots.map((slot, i) => (
                    <button
                      key={`empty-${slot.slotNum}`}
                      type="button"
                      onClick={() => { setSelectedSlot(slot.slotNum); setEmbarkOpen(true); }}
                      className="hk-card hk-card-interactive hk-enter group p-4 min-h-[8.5rem] flex flex-col items-start justify-between text-left border-dashed bg-transparent"
                      style={{ '--i': activeSlots.length + i }}
                    >
                      <span className="grid place-items-center w-9 h-9 rounded-xl bg-gray-500/10 text-gray-400 group-hover:bg-fantasy-accent group-hover:text-black transition-colors">
                        <Plus size={18} />
                      </span>
                      <span>
                        <span className="block font-semibold text-sm text-gray-200 group-hover:text-gray-50">{t('dashboard.new_adventure', 'New Adventure')}</span>
                        <span className="block text-xs text-gray-500 mt-0.5">{t('dashboard.new_adventure_desc', 'Select realm & class to start journey')}</span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}
        </section>
      </main>

      <CharacterCreatorModal
        isOpen={creatorOpen}
        onClose={() => setCreatorOpen(false)}
        onCreateCharacter={createCharacter}
      />

      <EmbarkationModal
        isOpen={embarkOpen}
        onClose={() => setEmbarkOpen(false)}
        character={character}
        scenarios={scenarios}
        availableTags={availableTags}
        targetSlot={selectedSlot}
        onEmbark={handleEmbark}
      />

      <SettingsModal
        isOpen={settingsModalOpen}
        onClose={() => setSettingsModalOpen(false)}
        settingsHook={settings}
        user={user}
      />
    </div>
  );
};

export default DashboardView;
