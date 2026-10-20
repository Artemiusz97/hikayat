import React, { useState, useEffect, useCallback } from 'react';
import { LogOut, Play, Users, Sword, Sliders, RefreshCw, Sparkles, Trash2, Plus, LogIn, Compass, Globe } from 'lucide-react';
import SettingsModal from '../components/Settings/SettingsModal';
import CharacterCreatorModal from '../components/Character/CharacterCreatorModal';
import EmbarkationModal from '../components/Adventure/EmbarkationModal';
import { apiCall } from '../api/client';
import { useTranslation } from 'react-i18next';
import LanguageSwitcher from '../components/Common/LanguageSwitcher';
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
  onEndSession,
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
    if (refreshSession) {
      refreshSession();
    }
  }, [fetchSaves, refreshSession, character?.id]); // re-fetch when character changes

  const handleEmbark = async (config) => {
    await startSession(config.scenario, config.mode, {
       tags: config.tags,
       capacity: 4,
       ...config
    });
    if (refreshCharacter) {
      await refreshCharacter();
    }
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

  const slots = [];
  if (activeSession) {
    slots.push({ type: 'active', data: activeSession });
  }
  saves.forEach(s => {
    if (slots.length < 6) slots.push({ type: 'save', data: s });
  });
  while (slots.length < 6) {
    slots.push({ type: 'empty' });
  }

  return (
    <div className="h-full min-h-0 overflow-y-auto bg-fantasy-darker text-gray-100 flex flex-col font-sans selection:bg-fantasy-accent/30 custom-scrollbar">
      <header className="bg-fantasy-dark border-b border-fantasy-border px-3 sm:px-4 py-2.5 sm:py-4 flex items-center justify-between sticky top-0 z-20 shadow-md shrink-0">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <div className="bg-fantasy-accent/20 p-1.5 sm:p-2 rounded-lg border border-fantasy-accent/40 shadow-inner shrink-0">
            <Sword className="text-fantasy-accent" size={20} />
          </div>
          <div className="min-w-0">
            <h1 className="text-lg sm:text-xl font-rpg font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-amber-200 to-amber-500 truncate">
              HIKAYAT
            </h1>
            <span className="text-[10px] sm:text-xs text-fantasy-accent/80 font-mono tracking-widest uppercase block truncate">{t('dashboard.chronicles_console', 'Chronicles Console')}</span>
          </div>
        </div>
        <div className="flex items-center gap-1.5 sm:gap-3 shrink-0">
          <span className="text-xs sm:text-sm font-semibold text-gray-200 bg-black/30 px-2 sm:px-3 py-1 sm:py-1.5 rounded border border-fantasy-border/50 max-w-[120px] sm:max-w-none truncate">
            {user?.display_name || user?.username || t('dashboard.guest', 'Guest')}
          </span>
          <LanguageSwitcher settingsHook={settings} />
          <button onClick={() => setSettingsModalOpen(true)} className="p-1.5 sm:p-2 rounded bg-fantasy-dark hover:bg-black border border-fantasy-border text-gray-400 hover:text-fantasy-accent transition-colors" title={t('nav.settings')}>
            <Sliders size={16} />
          </button>
          <button onClick={logout} className="p-1.5 sm:p-2 rounded bg-fantasy-dark hover:bg-black border border-fantasy-border text-gray-400 hover:text-red-400 transition-colors" title={t('dashboard.logout')}>
            <LogOut size={16} />
          </button>
        </div>
      </header>

      <main className="flex-1 p-3.5 sm:p-6 pb-28 sm:pb-8 max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-4 lg:gap-8">
        
        {/* Mobile Navigation Tabs */}
        <div className="lg:hidden col-span-1 sticky top-[53px] z-10 bg-fantasy-darker/95 backdrop-blur-sm pt-1 pb-3 -mx-3.5 px-3.5 border-b border-fantasy-border/60">
          <div className="grid grid-cols-3 gap-1.5 bg-black/60 p-1 rounded-lg border border-fantasy-border/70 shadow-md">
            <button
              type="button"
              onClick={() => setMobileTab('adventures')}
              className={`py-2 px-1 text-xs font-bold rounded-md flex items-center justify-center gap-1.5 transition-all ${
                mobileTab === 'adventures'
                  ? 'bg-fantasy-accent text-black shadow'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              <Compass size={14} className={mobileTab === 'adventures' ? 'text-black' : 'text-fantasy-accent'} />
              <span className="truncate">{t('dashboard.adventures', 'Adventures')}</span>
              {(activeSession || character?.active_session_id) && (
                <span className={`w-2 h-2 rounded-full ${mobileTab === 'adventures' ? 'bg-black' : 'bg-fantasy-accent animate-pulse'}`} />
              )}
            </button>

            <button
              type="button"
              onClick={() => setMobileTab('characters')}
              className={`py-2 px-1 text-xs font-bold rounded-md flex items-center justify-center gap-1.5 transition-all ${
                mobileTab === 'characters'
                  ? 'bg-fantasy-accent text-black shadow'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              <Users size={14} className={mobileTab === 'characters' ? 'text-black' : 'text-fantasy-accent'} />
              <span className="truncate">{t('dashboard.characters', 'Characters')}</span>
              <span className={`text-[10px] px-1 py-0.2 rounded font-mono ${mobileTab === 'characters' ? 'bg-black/20 text-black font-bold' : 'text-gray-500'}`}>
                {characters.length}
              </span>
            </button>

            <button
              type="button"
              onClick={() => setMobileTab('lobbies')}
              className={`py-2 px-1 text-xs font-bold rounded-md flex items-center justify-center gap-1.5 transition-all ${
                mobileTab === 'lobbies'
                  ? 'bg-fantasy-accent text-black shadow'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-white/5'
              }`}
            >
              <Globe size={14} className={mobileTab === 'lobbies' ? 'text-black' : 'text-fantasy-accent'} />
              <span className="truncate">{t('dashboard.lobbies', 'Lobbies')}</span>
              {lobbies.length > 0 && (
                <span className={`text-[10px] px-1 py-0.2 rounded font-mono ${mobileTab === 'lobbies' ? 'bg-black/20 text-black font-bold' : 'text-gray-500'}`}>
                  {lobbies.length}
                </span>
              )}
            </button>
          </div>
        </div>

        {/* Left Column: Roster & Lobbies */}
        <div className={`lg:col-span-4 space-y-4 lg:space-y-6 ${mobileTab === 'characters' || mobileTab === 'lobbies' ? 'block' : 'hidden lg:block'}`}>
           <div className={`bg-fantasy-panel border border-fantasy-border rounded-lg shadow-lg p-4 sm:p-5 ${mobileTab === 'characters' ? 'block' : 'hidden lg:block'}`}>
             <div className="flex items-center justify-between mb-4">
               <h2 className="text-sm font-bold uppercase tracking-widest text-fantasy-accent flex items-center gap-2">
                 <Users size={16} /> {t('dashboard.characters')}
               </h2>
               <span className="text-xs text-gray-400">{characters.length} / 6</span>
             </div>
             
             <div className="space-y-3">
                {characters.map(c => {
                  const isActive = character?.id === c.id;
                  const hasActiveSession = Boolean(c.active_session_id);
                  return (
                    <div
                      key={c.id}
                      onClick={async () => {
                        await switchCharacter(c.id);
                        if (refreshSession) refreshSession();
                        setMobileTab('adventures');
                      }}
                      className={`p-3 rounded border cursor-pointer flex items-center justify-between transition-all ${isActive ? 'bg-fantasy-accent/15 border-fantasy-accent' : 'bg-black/30 border-fantasy-border hover:border-gray-500'}`}
                    >
                      <div className="flex-1 min-w-0 pr-2">
                        <div className="font-bold text-gray-100 flex items-center gap-2 flex-wrap">
                          <span className="truncate">{c.name}</span>
                          {hasActiveSession && (
                            <span className="text-[10px] font-semibold text-amber-300 bg-amber-950/60 border border-amber-500/40 px-1.5 py-0.5 rounded font-mono uppercase tracking-wide">
                              {t('dashboard.in_adventure', 'In Adventure')}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-gray-400 flex items-center gap-1.5 flex-wrap mt-0.5">
                          <span>Lv {c.level} {c.char_class}</span>
                          {(c.gender || c.race) && <span className="text-gray-600">•</span>}
                          {c.gender && (
                            <span className="px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40 text-[10px] font-medium leading-none">
                              {c.gender}
                            </span>
                          )}
                          {c.race && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40 text-[10px] font-medium leading-none">
                              {c.race}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                         {hasActiveSession && (
                           <button
                             type="button"
                             onClick={async (e) => {
                               e.stopPropagation();
                               if (!isActive) {
                                 await switchCharacter(c.id);
                                 if (refreshSession) refreshSession();
                               }
                               onResumeSession();
                             }}
                             className="lg:hidden px-2.5 py-1 bg-fantasy-accent text-black font-bold text-[11px] rounded flex items-center gap-1 shadow hover:bg-amber-400 active:scale-95 transition-all"
                             title={t("dashboard.resume", "Resume")}
                           >
                             <Play size={10} className="fill-current" />
                             <span>{t("dashboard.resume", "Resume")}</span>
                           </button>
                         )}
                         {isActive && <div className="w-2 h-2 rounded-full bg-fantasy-accent animate-pulse" />}
                         <button onClick={(e) => { e.stopPropagation(); deleteCharacter(c.id); }} className="text-red-400/50 hover:text-red-400 p-1"><Trash2 size={14}/></button>
                      </div>
                    </div>
                  );
                })}
                
                {characters.length < 6 && (
                  <button onClick={() => setCreatorOpen(true)} className="w-full p-3 rounded border border-dashed border-fantasy-border text-gray-400 hover:border-fantasy-accent hover:text-fantasy-accent transition-all flex items-center justify-center gap-2">
                    <Plus size={16} /> {t('dashboard.create_character', 'Create Character')}
                  </button>
                )}
             </div>
           </div>
           
           {/* Lobbies */}
           <div className={`bg-fantasy-panel border border-fantasy-border rounded-lg shadow-lg p-4 sm:p-5 ${mobileTab === 'lobbies' ? 'block' : 'hidden lg:block'}`}>
              <div className="flex items-center justify-between mb-4">
               <h2 className="text-sm font-bold uppercase tracking-widest text-fantasy-accent flex items-center gap-2">
                 <Globe size={16} /> {t('dashboard.lobbies', 'Lobbies')}
               </h2>
               <button onClick={fetchLobbies} className="text-gray-400 hover:text-white"><RefreshCw size={14}/></button>
             </div>
             
             <div className="space-y-3 max-h-48 overflow-y-auto custom-scrollbar">
                {lobbies.length === 0 ? <div className="text-xs text-gray-500 text-center py-2">{t('dashboard.no_lobbies', 'No active lobbies')}</div> : 
                   lobbies.map(l => (
                     <div key={l.id} className="p-2 bg-black/40 border border-fantasy-border rounded flex justify-between items-center">
                       <div>
                         <div className="text-xs font-bold text-gray-200">{l.scene_title}</div>
                         <div className="text-[10px] text-gray-400">Host: {l.host_name}</div>
                       </div>
                       <button onClick={() => joinSession(l.id)} className="px-2 py-1 bg-fantasy-accent/20 text-fantasy-accent rounded text-xs">{t('dashboard.join', 'Join')}</button>
                     </div>
                   ))
                }
             </div>
             
             <div className="mt-4 pt-4 border-t border-fantasy-border flex gap-2">
               <input type="text" placeholder={t('dashboard.invite_code_placeholder', 'Invite Code...')} value={joinCode} onChange={(e) => setJoinCode(e.target.value)} className="flex-1 bg-black/50 border border-fantasy-border rounded px-2 text-xs text-gray-100" />
               <button onClick={() => joinSession(joinCode)} disabled={!joinCode.trim()} className="px-3 py-1.5 bg-fantasy-dark border border-fantasy-border rounded hover:bg-fantasy-accent/20 text-xs flex items-center gap-1">
                 <LogIn size={14} /> {t('dashboard.join', 'Join')}
               </button>
             </div>
           </div>
        </div>
        
        {/* Right Column: Adventure Slots */}
        <div className={`lg:col-span-8 ${mobileTab === 'adventures' ? 'block' : 'hidden lg:block'}`}>
           {/* Mobile Quick Character Selector Bar */}
           <div className="lg:hidden mb-3 bg-fantasy-panel border border-fantasy-border/80 rounded-lg p-2.5 shadow-md">
             <div className="flex items-center justify-between mb-1.5 px-0.5">
               <span className="text-[10px] uppercase font-bold text-gray-400 tracking-wider flex items-center gap-1">
                 <Users size={11} className="text-fantasy-accent" />
                 {t('dashboard.select_hero', 'Active Character')}
               </span>
               <button
                 type="button"
                 onClick={() => setMobileTab('characters')}
                 className="text-[10px] text-fantasy-accent hover:underline flex items-center gap-0.5 font-semibold"
               >
                 {t('dashboard.manage_all', 'Manage All ({{count}})', { count: characters.length })} →
               </button>
             </div>
             <div className="flex items-center gap-2 overflow-x-auto no-scrollbar py-0.5">
               {characters.map(c => {
                 const isSelected = character?.id === c.id;
                 const hasActiveSession = Boolean(c.active_session_id);
                 return (
                   <button
                     key={c.id}
                     type="button"
                     onClick={async () => {
                       await switchCharacter(c.id);
                       if (refreshSession) refreshSession();
                     }}
                     className={`shrink-0 px-2.5 py-1.5 rounded-md border text-xs font-bold flex items-center gap-1.5 transition-all ${
                       isSelected
                         ? 'bg-fantasy-accent/20 border-fantasy-accent text-fantasy-accent shadow-sm'
                         : 'bg-black/40 border-fantasy-border text-gray-400 hover:border-gray-500 hover:text-gray-200'
                     }`}
                   >
                     {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-fantasy-accent animate-pulse" />}
                     <span>{c.name}</span>
                     {hasActiveSession && (
                       <span className="text-[9px] px-1 py-0.2 rounded bg-amber-950/80 text-amber-300 border border-amber-600/40 font-mono">
                         LIVE
                       </span>
                     )}
                   </button>
                 );
               })}
               {characters.length < 6 && (
                 <button
                   type="button"
                   onClick={() => setCreatorOpen(true)}
                   className="shrink-0 px-2 py-1.5 rounded-md border border-dashed border-fantasy-border text-gray-400 hover:border-fantasy-accent hover:text-fantasy-accent text-xs flex items-center gap-1"
                 >
                   <Plus size={12} /> {t('common.new', 'New')}
                 </button>
               )}
             </div>
           </div>

           <div className="bg-fantasy-panel border border-fantasy-border rounded-lg shadow-lg p-4 sm:p-6 min-h-full">
              <div className="flex items-center justify-between mb-4 sm:mb-6 border-b border-fantasy-border pb-3 sm:pb-4">
                 <div>
                   <h2 className="text-base sm:text-lg font-bold text-gray-100 flex items-center gap-2">
                     <Compass className="text-fantasy-accent" />
                     {t('dashboard.adventures_for', { name: character?.name || '...', defaultValue: `Adventures for ${character?.name || '...'}` })}
                   </h2>
                   <p className="text-xs text-gray-400 mt-0.5 sm:mt-1">{t('dashboard.adventures_subtitle', 'Manage active sessions and checkpoints, or embark on a new journey.')}</p>
                 </div>
              </div>
              
              {!character ? (
                 <div className="flex flex-col items-center justify-center py-16 sm:py-20 text-gray-500">
                    <Sword size={48} className="mb-4 opacity-20" />
                    <p className="text-sm text-center px-4">{t('dashboard.no_character_selected', 'Select or create a character to view adventures.')}</p>
                    <button
                      type="button"
                      onClick={() => setCreatorOpen(true)}
                      className="mt-4 px-4 py-2 rounded bg-fantasy-accent text-black font-bold text-xs flex items-center gap-1.5 shadow"
                    >
                      <Plus size={14} /> {t('dashboard.create_character', 'Create Character')}
                    </button>
                 </div>
              ) : (
                 <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                   {slots.map((slot, idx) => {
                     if (slot.type === 'active') {
                       return (
                         <div key={`active-${idx}`} className="p-4 rounded-lg bg-fantasy-accent/10 border border-fantasy-accent flex flex-col justify-between shadow-lg">
                            <div>
                               <div className="flex items-center justify-between mb-2">
                                 <span className="text-[10px] uppercase font-bold text-fantasy-accent px-2 py-0.5 bg-fantasy-accent/20 rounded border border-fantasy-accent/40">
                                   {t('dashboard.active_session', { slot: idx + 1, defaultValue: `Active Session • Slot #${idx + 1}` })}
                                 </span>
                                 <span className="text-[10px] text-fantasy-accent font-mono uppercase">{t("dashboard.live", "Live")}</span>
                               </div>
                               <div className="font-bold text-gray-100 text-sm">{slot.data.scene_title || slot.data.scenario_display_name || slot.data.scenario}</div>
                               <div className="text-xs text-gray-400 mt-1 line-clamp-2">{slot.data.narrative_snippet || t("dashboard.journey_continues", "Journey continues...")}</div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-fantasy-accent/30 flex gap-2">
                               <button
                                 onClick={onResumeSession}
                                 className="flex-1 py-2 sm:py-1.5 bg-fantasy-accent text-black font-bold text-xs rounded hover:bg-amber-400 active:scale-[0.99] transition-all flex items-center justify-center gap-1.5 shadow-md"
                               >
                                 <Play size={13} className="fill-current" />
                                 <span>{t("dashboard.resume", "Resume")}</span>
                               </button>
                               <button
                                 onClick={onEndSession}
                                 className="px-3 py-2 sm:py-1.5 border border-fantasy-accent/50 text-fantasy-accent text-xs rounded hover:bg-fantasy-accent/20 transition-colors"
                               >
                                 {t("dashboard.end", "End")}
                               </button>
                            </div>
                         </div>
                       );
                     }
                     if (slot.type === 'save') {
                       return (
                         <div key={`save-${idx}`} className="p-4 rounded-lg bg-black/40 border border-fantasy-border flex flex-col justify-between hover:border-gray-500 transition-colors">
                            <div>
                               <div className="flex items-center justify-between mb-2">
                                 <span className="text-[10px] uppercase font-bold text-gray-400 px-2 py-0.5 bg-black/60 rounded border border-fantasy-border/40">
                                   {t('dashboard.checkpoint', { slot: idx + 1, defaultValue: `Checkpoint • Slot #${idx + 1}` })}
                                 </span>
                                 <div className="flex items-center gap-1.5">
                                   <span className="text-[10px] text-gray-500 font-mono">{new Date(slot.data.saved_at * 1000).toLocaleDateString()}</span>
                                   <button onClick={(e) => handleDeleteSave(slot.data.slot_name, e)} className="text-red-400/50 hover:text-red-400 p-0.5" title={t("common.delete", "Delete")}>
                                     <Trash2 size={12} />
                                   </button>
                                 </div>
                               </div>
                               <div className="font-bold text-gray-200 text-sm">{slot.data.slot_name}</div>
                               <div className="text-xs text-gray-400 mt-1 line-clamp-2">{slot.data.scene_title || slot.data.scenario_display_name || slot.data.scenario}</div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-fantasy-border/50">
                               <button
                                 onClick={() => handleLoadSave(slot.data.slot_name)}
                                 className="w-full py-2 sm:py-1.5 bg-fantasy-dark border border-fantasy-border hover:bg-white/5 text-gray-200 text-xs rounded transition-colors"
                               >
                                 {t("dashboard.load_checkpoint", "Load Checkpoint")}
                               </button>
                            </div>
                         </div>
                       );
                     }
                     
                     // Empty Slot with Stats Preview
                     const str = character.str_ ?? character.str ?? 1;
                     const per = character.per_ ?? character.per ?? 1;
                     const end = character.end_ ?? character.end ?? 1;
                     const cha = character.cha ?? 1;
                     const intVal = character.int_ ?? character.int ?? 1;
                     const agi = character.agi ?? 1;
                     const luk = character.luk ?? 1;
                     const hp = character.max_hp || (200 + end * 100);
                     const mp = character.max_mp || (50 + end * 25);

                     return (
                       <div
                         key={`empty-${idx}`}
                         onClick={() => setEmbarkOpen(true)}
                         className="p-4 rounded-lg border-2 border-dashed border-fantasy-border/70 hover:border-fantasy-accent bg-black/30 hover:bg-fantasy-accent/5 flex flex-col justify-between cursor-pointer transition-all duration-200 group min-h-[160px]"
                       >
                         <div>
                           <div className="flex items-center justify-between mb-1.5">
                             <span className="text-[10px] uppercase font-bold text-gray-400 px-2 py-0.5 bg-black/60 rounded border border-fantasy-border/40">
                               {t('dashboard.available_slot', { slot: idx + 1, defaultValue: `Slot #${idx + 1} • Available` })}
                             </span>
                             <span className="text-[10px] text-fantasy-accent font-semibold group-hover:translate-x-0.5 transition-transform flex items-center gap-0.5">
                               <Plus size={12} /> {t("dashboard.embark", "Embark")}
                             </span>
                           </div>

                           <div className="font-bold text-gray-200 text-sm group-hover:text-fantasy-accent transition-colors flex items-center gap-1.5">
                             <span>{t("dashboard.new_adventure", "New Adventure")}</span>
                           </div>

                           <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-1">
                             {t("dashboard.new_adventure_desc", "Select realm & class to start journey")}
                           </p>

                           {/* Stats Preview on Empty Slot */}
                           <div className="mt-2.5 pt-2 border-t border-fantasy-border/40">
                             <div className="flex items-center justify-between text-[10px] uppercase font-bold text-gray-400 mb-1">
                               <span>{t("dashboard.hero_stats_preview", "Hero Stats Preview")}</span>
                               <span className="text-gray-400 font-mono text-[9px]">{hp} {t("stats.hp", "HP")} • {mp} {t("stats.mp", "MP")}</span>
                             </div>
                             <div className="grid grid-cols-7 gap-1 text-center font-mono">
                               {[
                                 { label: 'STR', val: str },
                                 { label: 'PER', val: per },
                                 { label: 'END', val: end },
                                 { label: 'CHA', val: cha },
                                 { label: 'INT', val: intVal },
                                 { label: 'AGI', val: agi },
                                 { label: 'LUK', val: luk },
                               ].map((st) => (
                                 <div key={st.label} className="bg-black/50 border border-fantasy-border/50 rounded py-0.5 px-0.5" title={`${st.label}: ${st.val}`}>
                                   <div className="text-[8px] text-gray-400">{st.label}</div>
                                   <div className="text-[11px] font-bold text-fantasy-accent">{st.val}</div>
                                 </div>
                               ))}
                             </div>
                           </div>
                         </div>

                         <div className="mt-2 pt-2 border-t border-fantasy-border/30 flex justify-end">
                           <span className="text-[10px] font-bold text-fantasy-accent group-hover:underline flex items-center gap-1">
                             {t("dashboard.configure_loadout", "Configure Loadout →")}
                           </span>
                         </div>
                       </div>
                     );
                   })}
                 </div>
              )}
           </div>
        </div>
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
