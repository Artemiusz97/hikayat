import React, { useState, useEffect, useCallback } from 'react';
import { LogOut, Play, Users, Sword, Sliders, RefreshCw, Sparkles, Trash2, Plus, LogIn, Compass, Globe } from 'lucide-react';
import SettingsModal from '../components/Settings/SettingsModal';
import CharacterCreatorModal from '../components/Character/CharacterCreatorModal';
import EmbarkationModal from '../components/Adventure/EmbarkationModal';
import { apiCall } from '../api/client';
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
  onSessionLoaded
}) => {
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

  const settings = useSettings(user?.user_id);

  const fetchLobbies = useCallback(() => {
    setLoadingLobbies(true);
    apiCall('/api/adventure/lobbies')
      .then(data => setLobbies(data.lobbies || []))
      .catch(() => {})
      .finally(() => setLoadingLobbies(false));
  }, []);

  const fetchSaves = useCallback(() => {
    if (!user?.user_id || !character) return;
    setLoadingSaves(true);
    apiCall(`/api/saves/${user.user_id}`)
      .then(data => setSaves(data.saves || []))
      .catch(() => {})
      .finally(() => setLoadingSaves(false));
  }, [user?.user_id, character]);

  useEffect(() => {
    apiCall('/api/scenarios')
      .then(data => {
        const list = data.scenario_list || (Array.isArray(data.scenarios) ? data.scenarios : []);
        if (list.length > 0) setScenarios(list);
      })
      .catch(() => {});
      
    apiCall('/api/tags')
      .then(data => {
        const list = data.tag_list || (Array.isArray(data.tags) ? data.tags : Object.entries(data.tags || {}).map(([key, val]) => ({ key, ...val })));
        if (list.length > 0) setAvailableTags(list);
      })
      .catch(() => {});
      
    fetchLobbies();
  }, [fetchLobbies]);

  useEffect(() => {
    fetchSaves();
  }, [fetchSaves, character]); // re-fetch when character changes

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
    <div className="min-h-screen bg-fantasy-darker text-gray-100 flex flex-col font-sans selection:bg-fantasy-accent/30">
      <header className="bg-fantasy-dark border-b border-fantasy-border p-4 flex items-center justify-between sticky top-0 z-20 shadow-md">
        <div className="flex items-center gap-3">
          <div className="bg-fantasy-accent/20 p-2 rounded-lg border border-fantasy-accent/40 shadow-inner">
            <Sword className="text-fantasy-accent" size={24} />
          </div>
          <div>
            <h1 className="text-xl font-rpg font-bold tracking-widest text-transparent bg-clip-text bg-gradient-to-r from-amber-200 to-amber-500">
              HIKAYAT
            </h1>
            <span className="text-xs text-fantasy-accent/80 font-mono tracking-widest uppercase">Chronicles Console</span>
          </div>
        </div>
        <div className="flex items-center gap-4">
          <span className="text-sm font-semibold text-gray-200 bg-black/30 px-3 py-1.5 rounded border border-fantasy-border/50">
            {user?.display_name || user?.username || 'Guest'}
          </span>
          <button onClick={() => setSettingsModalOpen(true)} className="p-2 rounded bg-fantasy-dark hover:bg-black border border-fantasy-border text-gray-400 hover:text-fantasy-accent transition-colors" title="Settings">
            <Sliders size={18} />
          </button>
          <button onClick={logout} className="p-2 rounded bg-fantasy-dark hover:bg-black border border-fantasy-border text-gray-400 hover:text-red-400 transition-colors" title="Log Out">
            <LogOut size={18} />
          </button>
        </div>
      </header>

      <main className="flex-1 p-6 max-w-7xl mx-auto w-full grid grid-cols-1 lg:grid-cols-12 gap-8">
        
        {/* Left Column: Roster */}
        <div className="lg:col-span-4 space-y-6">
           <div className="bg-fantasy-panel border border-fantasy-border rounded-lg shadow-lg p-5">
             <div className="flex items-center justify-between mb-4">
               <h2 className="text-sm font-bold uppercase tracking-widest text-fantasy-accent flex items-center gap-2">
                 <Users size={16} /> Roster
               </h2>
               <span className="text-xs text-gray-400">{characters.length} / 6</span>
             </div>
             
             <div className="space-y-3">
                {characters.map(c => {
                  const isActive = character?.id === c.id;
                  return (
                    <div key={c.id} onClick={() => switchCharacter(c.id)} className={`p-3 rounded border cursor-pointer flex items-center justify-between transition-all ${isActive ? 'bg-fantasy-accent/15 border-fantasy-accent' : 'bg-black/30 border-fantasy-border hover:border-gray-500'}`}>
                      <div>
                        <div className="font-bold text-gray-100">{c.name}</div>
                        <div className="text-xs text-gray-400">Lv {c.level} {c.char_class}</div>
                      </div>
                      <div className="flex items-center gap-2">
                         {isActive && <div className="w-2 h-2 rounded-full bg-fantasy-accent animate-pulse" />}
                         <button onClick={(e) => { e.stopPropagation(); deleteCharacter(c.id); }} className="text-red-400/50 hover:text-red-400 p-1"><Trash2 size={14}/></button>
                      </div>
                    </div>
                  );
                })}
                
                {characters.length < 6 && (
                  <button onClick={() => setCreatorOpen(true)} className="w-full p-3 rounded border border-dashed border-fantasy-border text-gray-400 hover:border-fantasy-accent hover:text-fantasy-accent transition-all flex items-center justify-center gap-2">
                    <Plus size={16} /> Create Character
                  </button>
                )}
             </div>
           </div>
           
           {/* Lobbies */}
           <div className="bg-fantasy-panel border border-fantasy-border rounded-lg shadow-lg p-5">
              <div className="flex items-center justify-between mb-4">
               <h2 className="text-sm font-bold uppercase tracking-widest text-fantasy-accent flex items-center gap-2">
                 <Globe size={16} /> Lobbies
               </h2>
               <button onClick={fetchLobbies} className="text-gray-400 hover:text-white"><RefreshCw size={14}/></button>
             </div>
             
             <div className="space-y-3 max-h-48 overflow-y-auto custom-scrollbar">
                {lobbies.length === 0 ? <div className="text-xs text-gray-500 text-center py-2">No active lobbies</div> : 
                   lobbies.map(l => (
                     <div key={l.id} className="p-2 bg-black/40 border border-fantasy-border rounded flex justify-between items-center">
                       <div>
                         <div className="text-xs font-bold text-gray-200">{l.scene_title}</div>
                         <div className="text-[10px] text-gray-400">Host: {l.host_name}</div>
                       </div>
                       <button onClick={() => joinSession(l.id)} className="px-2 py-1 bg-fantasy-accent/20 text-fantasy-accent rounded text-xs">Join</button>
                     </div>
                   ))
                }
             </div>
             
             <div className="mt-4 pt-4 border-t border-fantasy-border flex gap-2">
               <input type="text" placeholder="Invite Code..." value={joinCode} onChange={(e) => setJoinCode(e.target.value)} className="flex-1 bg-black/50 border border-fantasy-border rounded px-2 text-xs text-gray-100" />
               <button onClick={() => joinSession(joinCode)} disabled={!joinCode.trim()} className="px-3 py-1.5 bg-fantasy-dark border border-fantasy-border rounded hover:bg-fantasy-accent/20 text-xs flex items-center gap-1">
                 <LogIn size={14} /> Join
               </button>
             </div>
           </div>
        </div>
        
        {/* Right Column: Adventure Slots */}
        <div className="lg:col-span-8">
           <div className="bg-fantasy-panel border border-fantasy-border rounded-lg shadow-lg p-6 min-h-full">
              <div className="flex items-center justify-between mb-6 border-b border-fantasy-border pb-4">
                 <div>
                   <h2 className="text-lg font-bold text-gray-100 flex items-center gap-2">
                     <Compass className="text-fantasy-accent" />
                     Adventures for {character?.name || '...'}
                   </h2>
                   <p className="text-xs text-gray-400 mt-1">Manage active sessions and checkpoints, or embark on a new journey.</p>
                 </div>
              </div>
              
              {!character ? (
                 <div className="flex flex-col items-center justify-center py-20 text-gray-500">
                    <Sword size={48} className="mb-4 opacity-20" />
                    <p>Select or create a character to view adventures.</p>
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
                                   Active Session • Slot #{idx + 1}
                                 </span>
                                 <span className="text-[10px] text-fantasy-accent font-mono uppercase">Live</span>
                               </div>
                               <div className="font-bold text-gray-100 text-sm">{slot.data.scene_title || slot.data.scenario}</div>
                               <div className="text-xs text-gray-400 mt-1 line-clamp-2">{slot.data.narrative_snippet || 'Journey continues...'}</div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-fantasy-accent/30 flex gap-2">
                               <button onClick={onResumeSession} className="flex-1 py-1.5 bg-fantasy-accent text-black font-bold text-xs rounded hover:bg-amber-400 transition-colors">Resume</button>
                               <button onClick={onEndSession} className="px-3 py-1.5 border border-fantasy-accent/50 text-fantasy-accent text-xs rounded hover:bg-fantasy-accent/20 transition-colors">End</button>
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
                                   Checkpoint • Slot #{idx + 1}
                                 </span>
                                 <div className="flex items-center gap-1.5">
                                   <span className="text-[10px] text-gray-500 font-mono">{new Date(slot.data.saved_at * 1000).toLocaleDateString()}</span>
                                   <button onClick={(e) => handleDeleteSave(slot.data.slot_name, e)} className="text-red-400/50 hover:text-red-400 p-0.5" title="Delete checkpoint">
                                     <Trash2 size={12} />
                                   </button>
                                 </div>
                               </div>
                               <div className="font-bold text-gray-200 text-sm">{slot.data.slot_name}</div>
                               <div className="text-xs text-gray-400 mt-1 line-clamp-2">{slot.data.scene_title}</div>
                            </div>
                            <div className="mt-4 pt-3 border-t border-fantasy-border/50">
                               <button onClick={() => handleLoadSave(slot.data.slot_name)} className="w-full py-1.5 bg-fantasy-dark border border-fantasy-border hover:bg-white/5 text-gray-200 text-xs rounded transition-colors">Load Checkpoint</button>
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
                               Slot #{idx + 1} • Available
                             </span>
                             <span className="text-[10px] text-fantasy-accent font-semibold group-hover:translate-x-0.5 transition-transform flex items-center gap-0.5">
                               <Plus size={12} /> Embark
                             </span>
                           </div>

                           <div className="font-bold text-gray-200 text-sm group-hover:text-fantasy-accent transition-colors flex items-center gap-1.5">
                             <span>New Adventure</span>
                           </div>

                           <p className="text-[11px] text-gray-400 mt-0.5 line-clamp-1">
                             Select realm &amp; class to start journey
                           </p>

                           {/* Stats Preview on Empty Slot */}
                           <div className="mt-2.5 pt-2 border-t border-fantasy-border/40">
                             <div className="flex items-center justify-between text-[10px] uppercase font-bold text-gray-400 mb-1">
                               <span>Hero Stats Preview</span>
                               <span className="text-gray-400 font-mono text-[9px]">{hp} HP • {mp} MP</span>
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
                             Configure Loadout &rarr;
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
