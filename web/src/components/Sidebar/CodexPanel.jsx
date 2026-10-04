import React, { useState } from 'react';
import { 
  BookOpen, Users, Flag, Globe, Heart, Shield, 
  Sparkles, Search, MessageCircle, MapPin, ChevronDown, ChevronRight, User, UserPlus, UserMinus,
  Crown, ShoppingBag, Swords, BedDouble
} from 'lucide-react';

const getRelationshipTier = (score) => {
  if (score >= 80) return { label: 'Devoted / In Love', color: 'text-pink-400', bg: 'bg-pink-500' };
  if (score >= 50) return { label: 'Close Companion', color: 'text-purple-400', bg: 'bg-purple-500' };
  if (score >= 25) return { label: 'Friendly Ally', color: 'text-blue-400', bg: 'bg-blue-500' };
  if (score >= 15) return { label: 'Friend', color: 'text-emerald-400', bg: 'bg-emerald-500' };
  if (score >= 5) return { label: 'Familiar', color: 'text-cyan-400', bg: 'bg-cyan-500' };
  if (score >= -5) return { label: 'Acquaintance', color: 'text-gray-400', bg: 'bg-gray-500' };
  if (score >= -30) return { label: 'Suspicious / Cold', color: 'text-amber-400', bg: 'bg-amber-500' };
  return { label: 'Hostile / Rival', color: 'text-red-400', bg: 'bg-red-500' };
};

const getReputationTier = (score) => {
  if (score >= 81) return { label: 'Exalted', color: 'text-emerald-300', bg: 'bg-emerald-400' };
  if (score >= 51) return { label: 'Honored', color: 'text-emerald-400', bg: 'bg-emerald-500' };
  if (score >= 21) return { label: 'Friendly', color: 'text-blue-400', bg: 'bg-blue-500' };
  if (score >= 1) return { label: 'Liked', color: 'text-cyan-400', bg: 'bg-cyan-500' };
  if (score >= -10) return { label: 'Neutral', color: 'text-gray-400', bg: 'bg-gray-500' };
  if (score >= -40) return { label: 'Unfavorable', color: 'text-amber-400', bg: 'bg-amber-500' };
  return { label: 'Hostile / Rival', color: 'text-red-400', bg: 'bg-red-500' };
};

const CodexPanel = ({ codexHook, session, user, onSessionUpdated, onRefreshCharacter, onOpenMerchant, onTriggerAction }) => {
  const { contacts, factions, lorebook, commitments = [], loading, factionHqAction, refreshCodex } = codexHook;
  const [subTab, setSubTab] = useState('contacts'); // 'contacts' | 'factions' | 'lore'
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNpc, setExpandedNpc] = useState(null);
  const [contactTab, setContactTab] = useState('persona'); // 'persona' | 'relations' | 'intimate'
  const [expandedFaction, setExpandedFaction] = useState(null);
  const [loreFilter, setLoreFilter] = useState('all'); // 'all' | 'commitments'
  const [companionBusy, setCompanionBusy] = useState(null);
  const [factionBusy, setFactionBusy] = useState(null);
  const [companionFeedback, setCompanionFeedback] = useState(null);

  const partyNpcNames = new Set(
    (session?.party_npcs || []).map(p => (p.name || '').toLowerCase())
  );

  const handleToggleCompanion = async (npcName, isInParty) => {
    if (!session?.id || !user?.user_id) return;
    setCompanionBusy(npcName);
    setCompanionFeedback(null);
    try {
      const res = await fetch('/api/party/companion', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: session.id,
          npc_name: npcName,
          action: isInParty ? 'dismiss' : 'recruit',
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setCompanionFeedback({ type: 'error', text: data.detail || 'Could not update party.' });
      } else {
        setCompanionFeedback({ type: 'ok', text: data.message || 'Party updated.' });
        if (onSessionUpdated && Array.isArray(data.party_npcs)) {
          onSessionUpdated({ ...session, party_npcs: data.party_npcs });
        }
      }
    } catch (err) {
      setCompanionFeedback({ type: 'error', text: err.message });
    } finally {
      setCompanionBusy(null);
    }
  };

  const handleFactionOp = async (factionId, action) => {
    if (!factionHqAction || factionBusy) return;
    setFactionBusy(`${factionId}:${action}`);
    setCompanionFeedback(null);
    try {
      const data = await factionHqAction(factionId, action);
      if (data?.message) {
        setCompanionFeedback({ type: 'ok', text: data.message });
      }
      if (action === 'rest' && onRefreshCharacter) {
        onRefreshCharacter();
      }
      if (action === 'quartermaster') {
        if (data?.merchant && onSessionUpdated) {
          onSessionUpdated({ ...session, merchant: data.merchant });
        }
        if (onOpenMerchant) onOpenMerchant();
      }
      if (action === 'bounty') {
        if (refreshCodex) refreshCodex();
      }
      if (action === 'promote' && data && !data.auto_promoted && data.action_prompt && onTriggerAction) {
        await onTriggerAction({ custom_action_text: data.action_prompt });
      }
    } catch (err) {
      setCompanionFeedback({ type: 'error', text: err.message || 'Faction operation failed.' });
    } finally {
      setFactionBusy(null);
    }
  };


  // Filter contacts
  const filteredContacts = contacts.filter(c => {
    const q = searchQuery.toLowerCase();
    const name = (c.name || '').toLowerCase();
    const role = (c.basic_info?.role || c.basic_info?.occupation || '').toLowerCase();
    const faction = (c.basic_info?.faction || '').toLowerCase();
    return name.includes(q) || role.includes(q) || faction.includes(q);
  });

  // Filter factions
  const filteredFactions = factions.filter(f => {
    const q = searchQuery.toLowerCase();
    const name = (f.name || f.faction_id || '').toLowerCase();
    const desc = (f.description || '').toLowerCase();
    return name.includes(q) || desc.includes(q);
  });

  // Lorebook entities & commitments
  const loreEntities = lorebook.entities || [];
  const filteredLore = loreEntities.filter(e => {
    const q = searchQuery.toLowerCase();
    const name = (e.name || '').toLowerCase();
    const desc = (e.description || '').toLowerCase();
    return name.includes(q) || desc.includes(q);
  });

  const filteredCommitments = (commitments || []).filter(c => {
    const q = searchQuery.toLowerCase();
    const text = (c.description || c.summary || c.promise || c.title || '').toLowerCase();
    const npc = (c.npc_name || c.target_npc || '').toLowerCase();
    return text.includes(q) || npc.includes(q);
  });

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-4 space-y-4">
      
      {/* Top Header & Subtabs */}
      <div className="space-y-3 border-b border-fantasy-border pb-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen size={17} className="text-fantasy-accent" />
            <h3 className="font-rpg font-bold text-sm text-gray-100 uppercase tracking-wider">World Codex</h3>
          </div>
          <span className="text-[11px] font-mono text-gray-400">
            {subTab === 'contacts' ? `${contacts.length} NPCs` : subTab === 'factions' ? `${factions.length} Factions` : `${loreEntities.length} Lore`}
          </span>
        </div>

        {/* Subtabs Selector */}
        <div className="flex bg-black/60 p-1 rounded-md border border-fantasy-border/60 gap-1">
          <button
            onClick={() => { setSubTab('contacts'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'contacts' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Users size={12} />
            <span>Contacts</span>
          </button>

          <button
            onClick={() => { setSubTab('factions'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'factions' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Flag size={12} />
            <span>Factions</span>
          </button>

          <button
            onClick={() => { setSubTab('lore'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-xs font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'lore' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Globe size={12} />
            <span>Lore</span>
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search size={13} className="absolute left-2.5 top-2.5 text-gray-500" />
          <input
            type="text"
            placeholder={`Search ${subTab}...`}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full bg-black/60 border border-fantasy-border/60 pl-8 pr-3 py-1.5 rounded text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fantasy-accent/50"
          />
        </div>
      </div>

      {/* Companion Action Feedback */}
      {companionFeedback && (
        <div className={`px-3 py-1.5 rounded text-xs border flex items-center justify-between ${
          companionFeedback.type === 'error'
            ? 'bg-red-950/60 border-red-800/60 text-red-200'
            : 'bg-emerald-950/60 border-emerald-800/60 text-emerald-200'
        }`}>
          <span>{companionFeedback.text}</span>
          <button
            onClick={() => setCompanionFeedback(null)}
            className="text-[10px] opacity-70 hover:opacity-100 ml-2"
          >
            ✕
          </button>
        </div>
      )}

      {/* Content View */}
      {loading && contacts.length === 0 ? (
        <p className="text-xs text-gray-500 italic text-center py-8">Consulting codex archives...</p>
      ) : (
        <div className="space-y-2.5 max-h-[26rem] overflow-y-auto custom-scrollbar pr-1">
          
          {/* 1. CONTACTS TAB */}
          {subTab === 'contacts' && (
            filteredContacts.length === 0 ? (
              <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                <Users size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">No matching contacts recorded yet.</p>
              </div>
            ) : (
              filteredContacts.map(npc => {
                const score = npc.relationship_score || npc.affinity || 0;
                const tier = getRelationshipTier(score);
                const isExpanded = expandedNpc === (npc.id || npc.name);
                const isRomantic = (npc.track === 'romantic') || (npc.relations?.track === 'romantic') || score >= 50;
                const isInParty = partyNpcNames.has((npc.name || '').toLowerCase());
                const canRecruit = score >= 15;

                const basic = npc.basic_info || {};
                const traits = npc.unlocked_traits || [];
                const preferences = npc.preferences || npc.likes || [];
                const dislikes = npc.dislikes || basic.dislikes || [];
                const memories = npc.intimate_memories || [];
                const appearance = npc.appearance || {};
                const familyTree = npc.family_tree || {};
                const relations = npc.relations || {};
                const infoLevel = npc.info_level ?? 0;
                const skillMod = npc.skill_modifier ?? Math.floor(Math.max(0, score) / 20);

                return (
                  <div 
                    key={npc.id || npc.name}
                    className="bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border rounded-lg p-3 space-y-2 transition-all"
                  >
                    {/* Header */}
                    <div 
                      onClick={() => setExpandedNpc(isExpanded ? null : (npc.id || npc.name))}
                      className="flex items-start justify-between cursor-pointer select-none"
                    >
                      <div className="flex items-center gap-2.5">
                        <div className={`w-9 h-9 rounded-full flex items-center justify-center border font-bold text-xs shrink-0 ${
                          isRomantic 
                            ? 'bg-pink-950/40 border-pink-700/60 text-pink-300' 
                            : 'bg-fantasy-dark border-fantasy-accent/40 text-fantasy-accent'
                        }`}>
                          {isRomantic ? <Heart size={15} /> : <User size={15} />}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-semibold text-xs text-gray-200">{npc.name}</span>
                            {isInParty && (
                              <span className="text-[9px] px-1 py-0.2 bg-purple-950/60 text-purple-300 rounded font-bold uppercase border border-purple-800/40">
                                In Party
                              </span>
                            )}
                            {isRomantic && (
                              <span className="text-[9px] px-1 py-0.2 bg-pink-950/60 text-pink-300 rounded font-bold uppercase border border-pink-800/40">
                                Romantic
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] text-gray-400 font-medium block truncate max-w-44">
                            {basic.role || basic.occupation || (basic.faction ? `${basic.faction} Member` : 'Acquaintance')}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1 text-right">
                        <div>
                          <span className={`text-[10px] font-bold block ${tier.color}`}>
                            {tier.label}
                          </span>
                          <span className="font-mono text-xs font-semibold text-gray-300">
                            {score > 0 ? `+${score}` : score}
                          </span>
                        </div>
                        {isExpanded ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
                      </div>
                    </div>

                    {/* Affinity Meter Bar */}
                    <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
                      <div 
                        className={`h-full ${tier.bg} transition-all duration-300`}
                        style={{ width: `${Math.max(5, Math.min(100, ((score + 100) / 200) * 100))}%` }}
                      />
                    </div>

                    {/* Expanded Details */}
                    {isExpanded && (
                      <div className="space-y-2.5 pt-2 border-t border-fantasy-border/40 text-xs text-gray-300">
                        
                        {/* Companion Recruit / Dismiss Action */}
                        <div className="flex items-center justify-between bg-black/40 p-2 rounded border border-fantasy-border/40">
                          <span className="text-[11px] text-gray-400">
                            {isInParty
                              ? 'Currently traveling in your party.'
                              : canRecruit
                                ? 'Friendly enough to join your party!'
                                : 'Requires Friend+ (+15 Affinity) to recruit.'}
                          </span>
                          {(isInParty || canRecruit) && (
                            <button
                              disabled={companionBusy === npc.name}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleToggleCompanion(npc.name, isInParty);
                              }}
                              className={`flex items-center gap-1 px-2.5 py-1 rounded text-[11px] font-bold border transition-all shrink-0 ${
                                isInParty
                                  ? 'bg-red-950/50 border-red-800/60 text-red-300 hover:bg-red-900/60'
                                  : 'bg-emerald-950/50 border-emerald-700/60 text-emerald-300 hover:bg-emerald-900/60'
                              }`}
                            >
                              {isInParty ? <UserMinus size={12} /> : <UserPlus size={12} />}
                              <span>{companionBusy === npc.name ? '...' : (isInParty ? 'Dismiss' : 'Recruit')}</span>
                            </button>
                          )}
                        </div>

                        {/* 3-Pill Contact Inspector Sub-Switcher */}
                        <div className="flex bg-black/60 p-0.5 rounded border border-fantasy-border/50 gap-1">
                          {[
                            { id: 'persona', label: '👤 Persona' },
                            { id: 'relations', label: '🌳 Relations & Family' },
                            { id: 'intimate', label: '🔥 Intimate & History' },
                          ].map(t => (
                            <button
                              key={t.id}
                              type="button"
                              onClick={(e) => { e.stopPropagation(); setContactTab(t.id); }}
                              className={`flex-1 py-1 px-1.5 rounded text-[10px] font-bold transition-colors ${
                                contactTab === t.id
                                  ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40'
                                  : 'text-gray-400 hover:text-gray-200'
                              }`}
                            >
                              {t.label}
                            </button>
                          ))}
                        </div>

                        {/* SUBTAB 1: PERSONA */}
                        {contactTab === 'persona' && (
                          <div className="space-y-2">
                            {/* Info Level & Skill Modifier */}
                            <div className="flex flex-wrap items-center gap-1.5">
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/30 font-mono">
                                Info Level: {infoLevel}/3
                              </span>
                              <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/40 font-mono">
                                Skill Modifier: +{skillMod}
                              </span>
                              {basic.race && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                                  {basic.race}
                                </span>
                              )}
                              {basic.gender && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                                  {basic.gender}
                                </span>
                              )}
                              {basic.age && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                                  Age {basic.age}
                                </span>
                              )}
                              {basic.grade && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40">
                                  {basic.grade}
                                </span>
                              )}
                              {basic.club && (
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                  Club: {basic.club}
                                </span>
                              )}
                            </div>

                            {/* Physical Appearance & Mannerisms */}
                            {(appearance.summary || basic.description || npc.description) && (
                              <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 text-[11px] text-gray-300 leading-snug">
                                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-0.5">
                                  Appearance & Mannerisms
                                </span>
                                {appearance.summary || basic.description || npc.description}
                              </div>
                            )}

                            {/* Unlocked Traits */}
                            {traits.length > 0 && (
                              <div>
                                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1">
                                  Known Traits
                                </span>
                                <div className="flex flex-wrap gap-1">
                                  {traits.map((t, idx) => (
                                    <span key={idx} className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border">
                                      {typeof t === 'string' ? t : (t.trait || t.name)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Likes / Preferences */}
                            {preferences.length > 0 && (
                              <div>
                                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1">
                                  Likes & Preferences
                                </span>
                                <div className="flex flex-wrap gap-1">
                                  {preferences.map((p, idx) => (
                                    <span key={idx} className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                      {typeof p === 'string' ? p : (p.preference || p.name)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {/* Dislikes */}
                            {dislikes.length > 0 && (
                              <div>
                                <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider block mb-1">
                                  Dislikes & Pet Peeves
                                </span>
                                <div className="flex flex-wrap gap-1">
                                  {dislikes.map((d, idx) => (
                                    <span key={idx} className="text-[10px] px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40">
                                      {typeof d === 'string' ? d : (d.dislike || d.name)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}

                        {/* SUBTAB 2: RELATIONS & FAMILY */}
                        {contactTab === 'relations' && (
                          <div className="space-y-2 bg-black/40 p-2.5 rounded border border-fantasy-border/40 text-[11px]">
                            <span className="text-[10px] font-bold text-fantasy-accent uppercase tracking-wider block">
                              Immediate Family Tree
                            </span>
                            {(familyTree.parents?.length > 0 || familyTree.siblings?.length > 0 || Array.isArray(familyTree) && familyTree.length > 0) ? (
                              <div className="space-y-1">
                                {Array.isArray(familyTree) ? (
                                  familyTree.map((mem, i) => (
                                    <div key={i} className="text-gray-300">
                                      • <strong>{mem.name || mem}</strong> {mem.relation ? `(${mem.relation})` : ''} {mem.occupation ? `— ${mem.occupation}` : ''}
                                    </div>
                                  ))
                                ) : (
                                  <>
                                    {familyTree.parents?.map((p, i) => (
                                      <div key={`p-${i}`} className="text-gray-300">
                                        • Parent: <strong>{typeof p === 'string' ? p : p.name}</strong> {p.occupation ? `(${p.occupation})` : ''} {p.status ? `[${p.status}]` : ''}
                                      </div>
                                    ))}
                                    {familyTree.siblings?.map((s, i) => (
                                      <div key={`s-${i}`} className="text-gray-300">
                                        • Sibling: <strong>{typeof s === 'string' ? s : s.name}</strong> {s.occupation || s.grade ? `(${s.occupation || s.grade})` : ''} {s.status ? `[${s.status}]` : ''}
                                      </div>
                                    ))}
                                  </>
                                )}
                              </div>
                            ) : (
                              <p className="text-gray-500 italic text-[10px]">No family records uncovered yet.</p>
                            )}

                            <div className="pt-1.5 border-t border-fantasy-border/30 space-y-1">
                              <span className="text-[10px] font-bold text-purple-300 uppercase tracking-wider block">
                                Social & Romantic Connections
                              </span>
                              {relations.current_partner && (
                                <div>💞 Partner: <strong className="text-pink-300">{relations.current_partner}</strong></div>
                              )}
                              {relations.secret_affair && (
                                <div>🤫 Secret Affair: <strong className="text-rose-400">{relations.secret_affair}</strong></div>
                              )}
                              {relations.ex_partners?.length > 0 && (
                                <div>💔 Ex-Partners: <span className="text-gray-300">{relations.ex_partners.join(', ')}</span></div>
                              )}
                              {relations.friends?.length > 0 && (
                                <div>🤝 Close Friends: <span className="text-cyan-300">{relations.friends.join(', ')}</span></div>
                              )}
                              {relations.rivals?.length > 0 && (
                                <div>⚔️ Rivals: <span className="text-amber-300">{relations.rivals.join(', ')}</span></div>
                              )}
                              {!relations.current_partner && !relations.secret_affair && !relations.ex_partners?.length && !relations.friends?.length && !relations.rivals?.length && (
                                <p className="text-gray-500 italic text-[10px]">No social ties documented yet.</p>
                              )}
                            </div>
                          </div>
                        )}

                        {/* SUBTAB 3: INTIMATE & HISTORY */}
                        {contactTab === 'intimate' && (
                          <div className="space-y-2 bg-black/40 p-2.5 rounded border border-fantasy-border/40 text-[11px]">
                            {(appearance.intimate_demeanor || appearance.intimate_dynamic || appearance.erotic_openness || appearance.openness || appearance.experience) && (
                              <div className="flex flex-wrap gap-1">
                                {appearance.intimate_demeanor && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
                                    Demeanor: {appearance.intimate_demeanor}
                                  </span>
                                )}
                                {appearance.intimate_dynamic && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-pink-950/60 text-pink-300 border border-pink-800/40">
                                    Dynamic: {appearance.intimate_dynamic}
                                  </span>
                                )}
                                {(appearance.erotic_openness || appearance.openness) && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                                    Openness: {appearance.erotic_openness || appearance.openness}
                                  </span>
                                )}
                                {appearance.experience && (
                                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-rose-950/60 text-rose-300 border border-rose-800/40">
                                    Exp: {appearance.experience}
                                  </span>
                                )}
                              </div>
                            )}

                            {appearance.anatomy && (
                              <div>
                                <span className="text-[10px] font-bold text-pink-400 uppercase block">Anatomy & Figure</span>
                                <p className="text-gray-300">{appearance.anatomy}</p>
                              </div>
                            )}

                            {(appearance.undergarments || appearance.lingerie) && (
                              <div>
                                <span className="text-[10px] font-bold text-purple-400 uppercase block">Undergarments</span>
                                <p className="text-gray-300">
                                  {typeof appearance.undergarments === 'object' && appearance.undergarments !== null
                                    ? [
                                        appearance.undergarments.bra ? `Bra: ${appearance.undergarments.bra}` : null,
                                        appearance.undergarments.underwear ? `Underwear: ${appearance.undergarments.underwear}` : null
                                      ].filter(Boolean).join(' • ')
                                    : (appearance.undergarments || appearance.lingerie)}
                                </p>
                              </div>
                            )}

                            {/* Turn-Ons & Erogenous Zones */}
                            {(() => {
                              const rawTurnOns = Array.isArray(appearance.turn_ons)
                                ? appearance.turn_ons
                                : (typeof appearance.turn_ons === 'string' ? appearance.turn_ons.split(',').map(s => s.trim()).filter(Boolean) : []);
                              const rawZones = Array.isArray(appearance.erogenous_zones)
                                ? appearance.erogenous_zones
                                : (typeof appearance.erogenous_zones === 'string' ? appearance.erogenous_zones.split(',').map(s => s.trim()).filter(Boolean) : []);
                              
                              const seen = new Set();
                              const uniqueItems = [];
                              for (const item of [...rawTurnOns, ...rawZones]) {
                                if (!item || ['none', 'unknown'].includes(item.toLowerCase().trim())) continue;
                                const base = item.toLowerCase().replace(/\s*\((physical|action)\)/i, '').trim();
                                if (!seen.has(base)) {
                                  seen.add(base);
                                  uniqueItems.push(item);
                                }
                              }

                              if (uniqueItems.length === 0) return null;

                              return (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-bold text-pink-400 uppercase block">Turn-Ons & Erogenous Zones</span>
                                  <div className="flex flex-wrap gap-1">
                                    {uniqueItems.map((k, i) => (
                                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-pink-950/40 text-pink-200 border border-pink-800/40">
                                        {k}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}

                            {/* Fetishes & Kinks */}
                            {(() => {
                              const rawKinks = Array.isArray(appearance.kinks)
                                ? appearance.kinks
                                : (typeof appearance.kinks === 'string' ? appearance.kinks.split(',').map(s => s.trim()).filter(Boolean) : (appearance.fetishes ? [String(appearance.fetishes)] : []));
                              const validKinks = rawKinks.filter(k => k && !['none', 'none (vanilla)', 'unknown'].includes(k.toLowerCase().trim()));
                              if (validKinks.length === 0) return null;

                              return (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-bold text-violet-400 uppercase block">Fetishes & Kinks</span>
                                  <div className="flex flex-wrap gap-1">
                                    {validKinks.map((kink, i) => (
                                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-violet-950/40 text-violet-200 border border-violet-800/40">
                                        {kink}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}

                            {/* Favorite Acts & Positions */}
                            {(() => {
                              const rawActs = Array.isArray(appearance.favorite_acts)
                                ? appearance.favorite_acts
                                : (typeof appearance.favorite_acts === 'string' ? appearance.favorite_acts.split(',').map(s => s.trim()).filter(Boolean) : []);
                              const rawPositions = Array.isArray(appearance.favorite_positions)
                                ? appearance.favorite_positions
                                : (typeof appearance.favorite_positions === 'string' ? appearance.favorite_positions.split(',').map(s => s.trim()).filter(Boolean) : []);
                              
                              const seen = new Set();
                              const uniqueFavs = [];
                              for (const item of [...rawActs, ...rawPositions]) {
                                if (!item || ['none', 'unknown'].includes(item.toLowerCase().trim())) continue;
                                const base = item.toLowerCase().trim();
                                if (!seen.has(base)) {
                                  seen.add(base);
                                  uniqueFavs.push(item);
                                }
                              }

                              if (uniqueFavs.length === 0) return null;

                              return (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-bold text-rose-400 uppercase block">Favorite Acts & Positions</span>
                                  <div className="flex flex-wrap gap-1">
                                    {uniqueFavs.map((act, i) => (
                                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-rose-950/40 text-rose-200 border border-rose-800/40">
                                        {act}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}

                            {/* Disliked Acts & Boundaries */}
                            {(() => {
                              const rawDislikes = Array.isArray(appearance.disliked_acts)
                                ? appearance.disliked_acts
                                : (typeof appearance.disliked_acts === 'string' ? appearance.disliked_acts.split(',').map(s => s.trim()).filter(Boolean) : []);
                              
                              const seen = new Set();
                              const uniqueDislikes = [];
                              for (const item of rawDislikes) {
                                if (!item || ['none', 'unknown'].includes(item.toLowerCase().trim())) continue;
                                const base = item.toLowerCase().trim();
                                if (!seen.has(base)) {
                                  seen.add(base);
                                  uniqueDislikes.push(item);
                                }
                              }

                              if (uniqueDislikes.length === 0) return null;

                              return (
                                <div className="space-y-1">
                                  <span className="text-[10px] font-bold text-gray-500 uppercase block">Disliked Acts & Boundaries</span>
                                  <div className="flex flex-wrap gap-1">
                                    {uniqueDislikes.map((act, i) => (
                                      <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-gray-950/40 text-gray-400 border border-gray-800/40">
                                        {act}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}

                            {(npc.past_intimate_history || (npc.past_intimate_entries && npc.past_intimate_entries.length > 0)) && (
                              <div>
                                <span className="text-[10px] font-bold text-gray-400 uppercase block">Past Intimate History</span>
                                {(npc.past_intimate_entries && npc.past_intimate_entries.length > 0) ? (
                                  <div className="space-y-0.5">
                                    {npc.past_intimate_entries.map((h, i) => (
                                      <p key={i} className="text-gray-300 italic">• {h}</p>
                                    ))}
                                  </div>
                                ) : Array.isArray(npc.past_intimate_history) ? (
                                  <div className="space-y-0.5">
                                    {npc.past_intimate_history.map((h, i) => (
                                      <p key={i} className="text-gray-300 italic">• {h}</p>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-gray-300 italic">{npc.past_intimate_history}</p>
                                )}
                              </div>
                            )}

                            {/* Shared Memories */}
                            {(() => {
                              const sharedMilestones = memories.filter(m => typeof m === 'string' ? !m.startsWith('Past History:') : true);
                              if (sharedMilestones.length === 0) {
                                if (!appearance.anatomy && !npc.past_intimate_history) {
                                  return <p className="text-gray-500 italic text-[10px]"> Deepen your bond or unlock higher Info Levels to reveal intimate details.</p>;
                                }
                                return null;
                              }

                              return (
                                <div className="pt-1">
                                  <span className="text-[10px] font-bold text-pink-400 uppercase tracking-wider flex items-center gap-1 mb-1">
                                    <Sparkles size={10} />
                                    <span>Shared Romantic Milestones</span>
                                  </span>
                                  <div className="space-y-1 bg-black/50 p-2 rounded border border-pink-900/40">
                                    {sharedMilestones.map((m, idx) => (
                                      <p key={idx} className="text-[11px] text-pink-200/90 leading-tight italic">
                                        • {typeof m === 'string' ? m : (m.summary || m.event)}
                                      </p>
                                    ))}
                                  </div>
                                </div>
                              );
                            })()}
                          </div>
                        )}

                      </div>
                    )}

                  </div>
                );
              })
            )
          )}

          {/* 2. FACTIONS TAB */}
          {subTab === 'factions' && (
            filteredFactions.length === 0 ? (
              <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                <Flag size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">No factions discovered yet.</p>
              </div>
            ) : (
              filteredFactions.map(faction => {
                const fid = faction.faction_id || faction.name;
                const rep = faction.reputation ?? faction.reputation_score ?? 0;
                const repTier = getReputationTier(rep);
                const isExpanded = expandedFaction === fid;
                const isMember = Boolean(faction.is_member);
                const playerRank = Number(faction.player_rank || 0);
                const eligibleRank = Number(faction.eligible_rank || 0);
                const canPromote = isMember && eligibleRank > playerRank && playerRank < 4;
                const canRest = rep >= 1;
                const roster = Array.isArray(faction.leadership_roster) ? faction.leadership_roster : [];
                const hierarchy = Array.isArray(faction.hierarchy) ? faction.hierarchy : [];
                const activePerks = Array.isArray(faction.active_perks) ? faction.active_perks : [];
                const rivalFactions = Array.isArray(faction.rival_faction_ids) ? faction.rival_faction_ids : [];

                return (
                  <div 
                    key={fid}
                    className="bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border rounded-lg p-3 space-y-2.5 transition-all"
                  >
                    <div
                      onClick={() => setExpandedFaction(isExpanded ? null : fid)}
                      className="flex justify-between items-start gap-1 cursor-pointer select-none"
                    >
                      <div className="min-w-0">
                        <h4 className="font-semibold text-xs text-gray-200 flex items-center gap-1.5 flex-wrap">
                          <Flag size={13} className="text-fantasy-accent shrink-0" />
                          <span>{faction.name || faction.faction_id}</span>
                          {isMember && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 font-bold uppercase">
                              Rank {playerRank || 1} {faction.player_title ? `• ${faction.player_title}` : 'Member'}
                            </span>
                          )}
                        </h4>
                        {faction.hq_location_id && (
                          <span className="text-[10px] text-gray-500 flex items-center gap-1 mt-0.5">
                            <MapPin size={10} />
                            <span>HQ: {faction.hq_location_id}</span>
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1 text-right shrink-0">
                        <div>
                          <span className={`text-[10px] font-bold block ${repTier.color}`}>
                            {faction.tier?.name || repTier.label}
                          </span>
                          <span className="font-mono text-xs font-semibold text-gray-300">
                            {rep > 0 ? `+${rep}` : rep} Rep
                          </span>
                        </div>
                        {isExpanded ? <ChevronDown size={14} className="text-gray-500" /> : <ChevronRight size={14} className="text-gray-500" />}
                      </div>
                    </div>

                    {(faction.description || faction.notes) && (
                      <p className="text-[11px] text-gray-400 leading-snug">{faction.description || faction.notes}</p>
                    )}

                    {/* Reputation Bar */}
                    <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
                      <div 
                        className={`h-full ${repTier.bg} transition-all duration-300`}
                        style={{ width: `${Math.max(5, Math.min(100, ((rep + 100) / 200) * 100))}%` }}
                      />
                    </div>

                    {/* Expanded Faction HQ & Rank 1-4 Leadership Roster */}
                    {isExpanded && (
                      <div className="pt-2 border-t border-fantasy-border/40 space-y-3 text-xs">
                        
                        {/* Active Faction Perks & Rival Factions */}
                        {(activePerks.length > 0 || rivalFactions.length > 0) && (
                          <div className="space-y-1.5 bg-black/40 p-2 rounded border border-fantasy-border/40">
                            {activePerks.length > 0 && (
                              <div>
                                <span className="text-[10px] font-bold text-emerald-400 uppercase tracking-wider block mb-1">
                                  ✨ Active Faction Perks
                                </span>
                                <div className="flex flex-wrap gap-1">
                                  {activePerks.map((perk, idx) => (
                                    <span key={idx} className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-950/50 text-emerald-200 border border-emerald-700/40">
                                      {typeof perk === 'string' ? perk : (perk.name || perk.description)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                            {rivalFactions.length > 0 && (
                              <div>
                                <span className="text-[10px] font-bold text-red-400 uppercase tracking-wider block mb-0.5">
                                  ⚔️ Rival Factions
                                </span>
                                <span className="text-[11px] text-gray-300">{rivalFactions.join(', ')}</span>
                              </div>
                            )}
                          </div>
                        )}

                        {/* Rank 1-4 Leadership Hierarchy Ladder */}
                        {roster.length > 0 && (
                          <div className="space-y-1.5">
                            <div className="flex items-center justify-between text-[10px] font-bold text-gray-400 uppercase tracking-wider">
                              <span className="flex items-center gap-1">
                                <Crown size={11} className="text-amber-400" />
                                <span>Leadership Hierarchy</span>
                              </span>
                              <span className="font-mono text-gray-500">Ranks 1–4</span>
                            </div>
                            <div className="space-y-1 bg-black/40 p-2 rounded border border-fantasy-border/40">
                              {[...roster].sort((a, b) => (b.rank || 0) - (a.rank || 0)).map((slot) => {
                                const hTier = hierarchy.find(h => h.rank === slot.rank);
                                const reqRep = hTier?.required_rep ?? (slot.rank === 4 ? 85 : slot.rank === 3 ? 60 : slot.rank === 2 ? 30 : 1);
                                const isLeader = slot.rank === 4 || hTier?.is_leader;
                                return (
                                  <div
                                    key={slot.rank}
                                    className={`flex items-center justify-between p-1.5 rounded border text-[11px] ${
                                      slot.is_player
                                        ? 'bg-amber-950/30 border-amber-600/50 text-amber-200'
                                        : 'bg-black/50 border-fantasy-border/30 text-gray-300'
                                    }`}
                                  >
                                    <div className="min-w-0">
                                      <div className="flex items-center gap-1.5">
                                        <span className="font-mono text-[10px] px-1 rounded bg-black/60 text-fantasy-accent border border-fantasy-border/50">
                                          R{slot.rank}
                                        </span>
                                        <span className="font-semibold truncate">{slot.title}</span>
                                        {isLeader && <Crown size={11} className="text-amber-400 shrink-0" />}
                                      </div>
                                      <span className="text-[10px] text-gray-400 block mt-0.5">
                                        Holder: <strong className="text-gray-200">{slot.is_vacant ? 'Vacant' : slot.name}</strong>
                                        {slot.is_player && (
                                          <span className="ml-1.5 text-[9px] px-1 bg-amber-500/20 text-amber-300 rounded border border-amber-500/40 font-bold uppercase">
                                            You
                                          </span>
                                        )}
                                      </span>
                                    </div>
                                    <span className="text-[10px] font-mono text-gray-500 shrink-0">
                                      Req +{reqRep}
                                    </span>
                                  </div>
                                );
                              })}
                            </div>
                          </div>
                        )}

                        {/* Faction HQ Operations Grid */}
                        <div className="space-y-1.5">
                          <span className="text-[10px] font-bold text-gray-400 uppercase tracking-wider block">
                            Faction Headquarters Operations
                          </span>
                          <div className="grid grid-cols-2 gap-1.5">
                            {/* Join or Leave */}
                            <button
                              disabled={Boolean(factionBusy)}
                              onClick={() => handleFactionOp(faction.faction_id, isMember ? 'leave' : 'join')}
                              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                                isMember
                                  ? 'bg-red-950/40 hover:bg-red-900/50 border-red-800/60 text-red-300'
                                  : 'bg-emerald-950/40 hover:bg-emerald-900/50 border-emerald-700/60 text-emerald-300'
                              }`}
                            >
                              <Flag size={12} />
                              <span>{isMember ? 'Leave Faction' : 'Pledge / Join'}</span>
                            </button>

                            {/* Safehouse Rest */}
                            <button
                              disabled={Boolean(factionBusy) || !canRest}
                              onClick={() => handleFactionOp(faction.faction_id, 'rest')}
                              title={canRest ? 'Recover full HP & MP at Faction Safehouse' : 'Requires Liked standing (+1 Rep)'}
                              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                                canRest
                                  ? 'bg-cyan-950/40 hover:bg-cyan-900/50 border-cyan-700/60 text-cyan-300'
                                  : 'bg-black/40 border-neutral-800 text-gray-600 cursor-not-allowed'
                              }`}
                            >
                              <BedDouble size={12} />
                              <span>Safehouse Rest</span>
                            </button>

                            {/* Quartermaster Shop */}
                            <button
                              disabled={Boolean(factionBusy)}
                              onClick={() => handleFactionOp(faction.faction_id, 'quartermaster')}
                              className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border bg-amber-950/40 hover:bg-amber-900/50 border-amber-700/60 text-amber-300 transition-all"
                            >
                              <ShoppingBag size={12} />
                              <span>Quartermaster</span>
                            </button>

                            {/* Promotion Trial */}
                            <button
                              disabled={Boolean(factionBusy) || !canPromote}
                              onClick={() => handleFactionOp(faction.faction_id, 'promote')}
                              title={
                                !isMember
                                  ? 'Join faction first'
                                  : canPromote
                                    ? `Challenge for Rank ${playerRank + 1}!`
                                    : 'Earn more Faction Reputation to unlock the next rank'
                              }
                              className={`flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border transition-all ${
                                canPromote
                                  ? 'bg-purple-950/50 hover:bg-purple-900/60 border-purple-600/60 text-purple-200 animate-pulse'
                                  : 'bg-black/40 border-neutral-800 text-gray-600 cursor-not-allowed'
                              }`}
                            >
                              <Swords size={12} />
                              <span>{canPromote ? `Promote (R${playerRank + 1})` : 'Promotion Locked'}</span>
                            </button>

                            {/* Faction Bounties */}
                            <button
                              disabled={Boolean(factionBusy)}
                              onClick={() => handleFactionOp(faction.faction_id, 'bounty')}
                              className="col-span-2 flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border bg-indigo-950/40 hover:bg-indigo-900/50 border-indigo-700/60 text-indigo-300 transition-all"
                            >
                              <span>📋 Faction Bounties</span>
                            </button>
                          </div>
                        </div>

                      </div>
                    )}
                  </div>
                );
              })
            )
          )}


          {/* 3. LOREBOOK TAB */}
          {subTab === 'lore' && (
            <div className="space-y-2.5">
              {/* Lore vs Commitments Filter Pills */}
              <div className="flex gap-1.5">
                <button
                  type="button"
                  onClick={() => setLoreFilter('all')}
                  className={`flex-1 py-1 px-2 rounded text-[10px] font-bold uppercase tracking-wider border transition-colors ${
                    loreFilter === 'all'
                      ? 'bg-fantasy-accent/20 text-fantasy-accent border-fantasy-accent/50'
                      : 'bg-black/40 text-gray-400 border-fantasy-border/50 hover:text-gray-200'
                  }`}
                >
                  📖 World Lore ({loreEntities.length})
                </button>
                <button
                  type="button"
                  onClick={() => setLoreFilter('commitments')}
                  className={`flex-1 py-1 px-2 rounded text-[10px] font-bold uppercase tracking-wider border transition-colors ${
                    loreFilter === 'commitments'
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/50'
                      : 'bg-black/40 text-gray-400 border-fantasy-border/50 hover:text-gray-200'
                  }`}
                >
                  🤝 Commitments ({(commitments || []).length})
                </button>
              </div>

              {loreFilter === 'commitments' ? (
                filteredCommitments.length === 0 ? (
                  <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                    <Shield size={24} className="mx-auto mb-1.5 opacity-40" />
                    <p className="text-xs">No active promises, debts, secrets, or pacts recorded.</p>
                  </div>
                ) : (
                  filteredCommitments.map((c, idx) => (
                    <div
                      key={c.id || idx}
                      className="bg-black/50 border border-amber-700/40 rounded-lg p-3 space-y-1.5"
                    >
                      <div className="flex justify-between items-start gap-1">
                        <h5 className="font-semibold text-xs text-amber-200">
                          {c.title || c.npc_name || c.target_npc || 'Active Commitment'}
                        </h5>
                        <span className="text-[9px] px-1.5 py-0.2 bg-amber-950/60 text-amber-300 rounded uppercase font-bold border border-amber-700/50">
                          {c.commitment_type || c.type || 'Promise'}
                        </span>
                      </div>
                      <p className="text-[11px] text-gray-300 leading-snug">
                        {c.description || c.summary || c.promise}
                      </p>
                      {(c.npc_name || c.status) && (
                        <div className="flex items-center justify-between text-[10px] text-gray-400 pt-1 border-t border-fantasy-border/30">
                          {c.npc_name && <span>👤 With: <strong>{c.npc_name}</strong></span>}
                          {c.status && <span className="font-mono text-amber-300">{c.status}</span>}
                        </div>
                      )}
                    </div>
                  ))
                )
              ) : filteredLore.length === 0 ? (
                <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                  <Globe size={24} className="mx-auto mb-1.5 opacity-40" />
                  <p className="text-xs">No lore entries documented yet.</p>
                </div>
              ) : (
                filteredLore.map((ent, idx) => (
                  <div 
                    key={ent.id || idx}
                    className="bg-black/50 border border-fantasy-border/60 rounded-lg p-3 space-y-1.5"
                  >
                    <div className="flex justify-between items-start gap-1">
                      <h5 className="font-semibold text-xs text-gray-200">{ent.name}</h5>
                      <span className="text-[9px] px-1.5 py-0.2 bg-black/60 text-gray-400 rounded uppercase font-bold border border-fantasy-border">
                        {ent.entity_type || 'Lore'}
                      </span>
                    </div>

                    {ent.description && (
                      <p className="text-[11px] text-gray-400 leading-snug">{ent.description}</p>
                    )}

                    {ent.location && (
                      <span className="text-[10px] text-gray-500 flex items-center gap-1">
                        <MapPin size={10} />
                        <span>{ent.location}</span>
                      </span>
                    )}
                  </div>
                ))
              )}
            </div>
          )}

        </div>
      )}

    </div>
  );
};

export default CodexPanel;
