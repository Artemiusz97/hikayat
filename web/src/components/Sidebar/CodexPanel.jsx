import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  BookOpen, Users, Flag, Globe, Heart, Shield, 
  Sparkles, Search, MessageCircle, MapPin, ChevronDown, ChevronRight, User, UserMinus,
  Crown, ShoppingBag, Swords, BedDouble, Lock, Scroll, Calendar, Clock
} from 'lucide-react';
import { StatusEffectBadge } from './CharacterSheet';

const formatPersonEntity = (item) => {
  if (!item) return '';
  if (typeof item === 'string') return item;
  const name = item.name || item.title || 'Unknown';
  const role = item.role || item.closeness || item.type || item.grade || item.relationship_type || '';
  return role ? `${name} (${role})` : name;
};

const formatTitle = (str) => {
  if (!str) return '';
  return String(str).replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
};

const formatRace = (str) => {
  if (!str) return '';
  const clean = String(str).trim().toLowerCase().replace(/-/g, '_');
  if (clean === 'human') return 'Human';
  if (clean === 'dark_elf') return 'Dark Elf';
  if (clean === 'irradiated_human') return 'Irradiated Human';
  if (clean === 'half_beast' || clean === 'halfbeast') return 'Half-Beast';
  if (clean === 'hybrid') return 'Hybrid';
  if (clean.includes(':')) {
    const [category, species] = clean.split(':');
    const catTitle = formatTitle(category);
    const specTitle = formatTitle(species);
    if (category === 'half_beast' || category === 'halfbeast') {
      return `${specTitle} Half-Beast`;
    }
    if (category === 'hybrid') {
      return `${specTitle} Hybrid`;
    }
    if (category === 'beastfolk') {
      return `${specTitle} Beastfolk`;
    }
    if (category === 'alien') {
      return `${specTitle} Alien`;
    }
    if (category === 'mutant') {
      return `${specTitle} Mutant`;
    }
    return `${specTitle} ${catTitle}`;
  }
  return formatTitle(clean);
};

const renderBulletPoints = (lines) => {
  if (!lines || !lines.length) return null;
  return (
    <div className="space-y-1">
      {lines.map((line, idx) => {
        let clean = String(line).replace(/^[•\-\*]\s*/, '').trim();
        clean = clean.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone');
        const match = clean.match(/^\*\*([^*]+)\*\*:\s*(.*)$/) || clean.match(/^([^:]+):\s*(.*)$/);
        if (match) {
          const [, label, val] = match;
          const isUnknown = /^\*?unknown\*?$/i.test(val.trim());
          return (
            <div key={idx} className="leading-relaxed text-gray-300 text-xs">
              • <strong className="text-gray-100">{label}</strong>:{' '}
              {isUnknown ? (
                <span className="text-gray-500 italic">Unknown</span>
              ) : (
                <span>{val}</span>
              )}
            </div>
          );
        }
        return (
          <div key={idx} className="leading-relaxed text-gray-300 text-xs">
            • {clean}
          </div>
        );
      })}
    </div>
  );
};

export const getRelationshipTier = (score, track = 'platonic', t = null) => {
  const isRom = String(track || '').toLowerCase() === 'romantic';
  let tierKey = 'stranger';
  let fallback = 'Stranger';
  let color = 'text-gray-400';
  let bg = 'bg-gray-500';

  if (score >= 250) {
    if (isRom) {
      tierKey = 'soulmate';
      fallback = 'Soulmate / Eternal Bond';
      color = 'text-pink-400';
      bg = 'bg-pink-500';
    } else {
      tierKey = 'sworn_lifelong_ally';
      fallback = 'Sworn Lifelong Ally';
      color = 'text-purple-400';
      bg = 'bg-purple-500';
    }
  } else if (score >= 200) {
    if (isRom) {
      tierKey = 'devoted_lovers';
      fallback = 'Devoted Lovers';
      color = 'text-pink-400';
      bg = 'bg-pink-500';
    } else {
      tierKey = 'confidant';
      fallback = 'Confidant';
      color = 'text-purple-400';
      bg = 'bg-purple-500';
    }
  } else if (score >= 150) {
    if (isRom) {
      tierKey = 'dating_partner';
      fallback = 'Dating / Confessed Partners';
      color = 'text-pink-400';
      bg = 'bg-pink-500';
    } else {
      tierKey = 'close_friend';
      fallback = 'Close Friend';
      color = 'text-blue-400';
      bg = 'bg-blue-500';
    }
  } else if (score >= 100) {
    if (isRom) {
      tierKey = 'mutual_attraction';
      fallback = 'Mutual Attraction / Crush';
      color = 'text-pink-300';
      bg = 'bg-pink-400';
    } else {
      tierKey = 'friend';
      fallback = 'Friend';
      color = 'text-emerald-400';
      bg = 'bg-emerald-500';
    }
  } else if (score >= 50) {
    tierKey = 'acquaintance';
    fallback = 'Acquaintance';
    color = 'text-cyan-400';
    bg = 'bg-cyan-500';
  } else if (score >= 0) {
    tierKey = 'stranger';
    fallback = 'Stranger';
    color = 'text-gray-400';
    bg = 'bg-gray-500';
  } else if (score >= -10) {
    tierKey = 'unfriendly';
    fallback = 'Unfriendly';
    color = 'text-amber-400';
    bg = 'bg-amber-500';
  } else if (score >= -30) {
    tierKey = 'distrusted';
    fallback = 'Distrusted';
    color = 'text-amber-500';
    bg = 'bg-amber-600';
  } else if (score >= -50) {
    tierKey = 'adversary';
    fallback = 'Adversary';
    color = 'text-orange-500';
    bg = 'bg-orange-600';
  } else if (score >= -70) {
    tierKey = 'hostile';
    fallback = 'Hostile';
    color = 'text-red-500';
    bg = 'bg-red-600';
  } else if (score >= -90) {
    tierKey = 'bitter_nemesis';
    fallback = 'Bitter Nemesis';
    color = 'text-red-600';
    bg = 'bg-red-700';
  } else {
    tierKey = 'mortal_foe';
    fallback = 'Mortal Foe';
    color = 'text-rose-600';
    bg = 'bg-rose-700';
  }

  const label = t ? t(`codex.tiers.${tierKey}`, fallback) : fallback;
  return { label, color, bg };
};

const getReputationTier = (score, t = null) => {
  let tierKey = 'hostile_rival';
  let fallback = 'Hostile / Rival';
  let color = 'text-red-400';
  let bg = 'bg-red-500';

  if (score >= 81) {
    tierKey = 'exalted'; fallback = 'Exalted'; color = 'text-emerald-300'; bg = 'bg-emerald-400';
  } else if (score >= 51) {
    tierKey = 'honored'; fallback = 'Honored'; color = 'text-emerald-400'; bg = 'bg-emerald-500';
  } else if (score >= 21) {
    tierKey = 'friendly'; fallback = 'Friendly'; color = 'text-blue-400'; bg = 'bg-blue-500';
  } else if (score >= 1) {
    tierKey = 'liked'; fallback = 'Liked'; color = 'text-cyan-400'; bg = 'bg-cyan-500';
  } else if (score >= -10) {
    tierKey = 'neutral'; fallback = 'Neutral'; color = 'text-gray-400'; bg = 'bg-gray-500';
  } else if (score >= -40) {
    tierKey = 'unfavorable'; fallback = 'Unfavorable'; color = 'text-amber-400'; bg = 'bg-amber-500';
  }

  const label = t ? t(`codex.rep_tiers.${tierKey}`, fallback) : fallback;
  return { label, color, bg };
};

const CodexPanel = ({
  codexHook,
  session,
  user,
  onSessionUpdated,
  onRefreshCharacter,
  onOpenMerchant,
  onTriggerAction,
  targetContactName,
}) => {
  const { t } = useTranslation();
  const { contacts, factions, lorebook, commitments = [], loading, factionHqAction, refreshCodex } = codexHook;
  const [subTab, setSubTab] = useState('contacts'); // 'contacts' | 'factions' | 'lore'
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNpc, setExpandedNpc] = useState(null);
  const [contactTab, setContactTab] = useState('persona'); // 'persona' | 'relations' | 'intimate'
  const [expandedFaction, setExpandedFaction] = useState(null);
  const [loreFilter, setLoreFilter] = useState('all'); // 'all' | 'commitments'
  const [companionBusy, setCompanionBusy] = useState(null);
  const [factionBusy, setFactionBusy] = useState(null);
  const [debugToggleOverrides, setDebugToggleOverrides] = useState({});
  const toggleDebugReveal = (npcKey, currentRevealed) => {
    setDebugToggleOverrides(prev => ({
      ...prev,
      [npcKey]: !currentRevealed,
    }));
  };
  const [companionFeedback, setCompanionFeedback] = useState(null);

  useEffect(() => {
    if (targetContactName) {
      setSubTab('contacts');
      setSearchQuery('');
      const matched = contacts.find(c => 
        (c.name || '').toLowerCase() === targetContactName.toLowerCase() ||
        (c.id || '').toLowerCase() === targetContactName.toLowerCase() ||
        (c.npc_id || '').toLowerCase() === targetContactName.toLowerCase()
      );
      if (matched) {
        setExpandedNpc(matched.id || matched.name);
      } else {
        setExpandedNpc(targetContactName);
      }
    }
  }, [targetContactName, contacts]);

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


  // Build unified discovered characters list combining contacts and any discovered person entities
  const knownCharacters = useMemo(() => {
    const list = [...contacts];
    const seen = new Set(list.map(c => (c.name || '').toLowerCase().trim()));

    const personEntities = (lorebook.entities || []).filter(e => e.entity_type === 'person');
    personEntities.forEach(p => {
      const pName = (p.name || '').toLowerCase().trim();
      const hasMet = Boolean(
        p.is_discovered ||
        p.relationship_score ||
        p.affinity ||
        p.is_contact ||
        p.contact_added ||
        p.last_in_person_ts
      );
      if (pName && !seen.has(pName) && hasMet) {
        seen.add(pName);
        list.push({
          ...p,
          id: p.id || p.npc_id || p.name,
          relationship_score: p.relationship_score || p.affinity || 0,
          basic_info: p.basic_info || {
            role: p.role,
            grade: p.grade,
            club: p.club,
            mannerisms: p.mannerisms,
            description: p.description,
            gender: p.gender,
            race: p.race,
            age: p.age,
          },
          appearance: p.appearance || {},
        });
      }
    });
    return list;
  }, [contacts, lorebook.entities]);

  // Filter known characters
  const filteredContacts = knownCharacters.filter(c => {
    const q = searchQuery.toLowerCase();
    const name = (c.name || '').toLowerCase();
    const role = (c.basic_info?.role || c.basic_info?.occupation || c.role || '').toLowerCase();
    const faction = (c.basic_info?.faction || c.faction || '').toLowerCase();
    const grade = (c.basic_info?.grade || c.grade || '').toLowerCase();
    const club = (c.basic_info?.club || c.club || '').toLowerCase();
    return name.includes(q) || role.includes(q) || faction.includes(q) || grade.includes(q) || club.includes(q);
  });

  // Filter factions
  const filteredFactions = factions.filter(f => {
    const q = searchQuery.toLowerCase();
    const name = (f.name || f.faction_id || '').toLowerCase();
    const desc = (f.description || '').toLowerCase();
    return name.includes(q) || desc.includes(q);
  });

  // World lore entities (strictly non-person entries: world events, locations, factions, artifacts, history)
  const loreEntities = (lorebook.entities || []).filter(e => e.entity_type !== 'person');
  const filteredLore = loreEntities.filter(e => {
    const q = searchQuery.toLowerCase();
    const name = (e.name || '').toLowerCase();
    const desc = (e.description || '').toLowerCase();
    const loc = (e.location || '').toLowerCase();
    return name.includes(q) || desc.includes(q) || loc.includes(q);
  });

  const filteredCommitments = (commitments || []).filter(c => {
    const q = searchQuery.toLowerCase();
    const text = (c.description || c.summary || c.promise || c.title || '').toLowerCase();
    const npc = (c.npc_name || c.target_npc || '').toLowerCase();
    return text.includes(q) || npc.includes(q);
  });

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-2.5 sm:p-3 space-y-2.5 min-h-full flex-1 flex flex-col">
      
      {/* Top Header & Subtabs */}
      <div className="space-y-2 border-b border-fantasy-border pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <BookOpen size={16} className="text-fantasy-accent" />
            <h3 className="font-rpg font-bold text-xs sm:text-sm text-gray-100 uppercase tracking-wider">{t('codex.title', 'World Codex')}</h3>
          </div>
          <span className="text-[10px] font-mono text-gray-400">
            {subTab === 'contacts'
              ? t('codex.npcs_count', { count: filteredContacts.length, defaultValue: `${filteredContacts.length} Characters` })
              : subTab === 'factions'
              ? t('codex.factions_count', { count: factions.length, defaultValue: `${factions.length} Factions` })
              : subTab === 'agenda'
              ? `${(commitments || []).length} Commitments`
              : t('codex.lore_count', { count: filteredLore.length, defaultValue: `${filteredLore.length} Lore` })}
          </span>
        </div>

        {/* Subtabs Selector */}
        <div className="flex bg-black/60 p-0.5 rounded-md border border-fantasy-border/60 gap-1">
          <button
            onClick={() => { setSubTab('contacts'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'contacts' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Users size={11} />
            <span>{t('codex.known_characters', 'Known Characters')}</span>
          </button>

          <button
            onClick={() => { setSubTab('factions'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'factions' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Flag size={11} />
            <span>{t('codex.factions', 'Factions')}</span>
          </button>

          <button
            onClick={() => { setSubTab('lore'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'lore' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Globe size={11} />
            <span>{t('codex.lore', 'Lore')}</span>
          </button>

          <button
            onClick={() => { setSubTab('agenda'); setSearchQuery(''); }}
            className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-colors ${
              subTab === 'agenda' 
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40' 
                : 'text-gray-400 hover:text-gray-200'
            }`}
          >
            <Calendar size={11} />
            <span>{t('codex.agenda', 'Agenda')}</span>
          </button>
        </div>

        {/* Search Bar */}
        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-2 text-gray-500" />
          <input
            type="text"
            placeholder={t('codex.search_placeholder', { category: t(`codex.${subTab}`, subTab), defaultValue: `Search ${subTab}...` })}
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            className="w-full bg-black/60 border border-fantasy-border/60 pl-7 pr-2.5 py-1 rounded text-xs text-gray-200 placeholder-gray-500 focus:outline-none focus:border-fantasy-accent/50"
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
        <div className="space-y-3 flex-1 flex flex-col">
          
          {/* 1. KNOWN CHARACTERS TAB */}
          {subTab === 'contacts' && (
            filteredContacts.length === 0 ? (
              <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                <Users size={24} className="mx-auto mb-1.5 opacity-40" />
                <p className="text-xs">{t('codex.no_characters', 'No characters discovered in the world yet.')}</p>
                <p className="text-[10px] text-gray-500 mt-1">Explore locations and meet characters in the story to reveal them here.</p>
              </div>
            ) : (
              filteredContacts.map(npc => {
                const score = npc.relationship_score || npc.affinity || 0;
                const isRomantic = (npc.track === 'romantic') || (npc.relations?.track === 'romantic');
                const tier = getRelationshipTier(score, isRomantic ? 'romantic' : 'platonic', t);
                const isExpanded = expandedNpc === (npc.id || npc.name);
                const isInParty = partyNpcNames.has((npc.name || '').toLowerCase());
                const basic = npc.basic_info || {};
                const isMerchant = /merchant|shopkeeper|vendor|apothecary|peddler|trader/i.test(basic.role || basic.occupation || npc.name || '');
                const isNonCombatScen = ['high_school_drama', 'high_school', 'slice_of_life', 'cozy_cafe'].includes((session?.scenario || '').toLowerCase());
                const isDialoguePartner = Boolean(session?.dialogue_partner && (session.dialogue_partner.toLowerCase() === (npc.name || '').toLowerCase()));
                const isDebugRevealed = (npc.id || npc.name) in debugToggleOverrides ? debugToggleOverrides[npc.id || npc.name] : Boolean(isDebugRevealed);
                const isDetailedUnlocked = score >= 100 || isInParty || isDialoguePartner || isDebugRevealed || Boolean(npc.debug_profile);
                const canRecruit = !isNonCombatScen && !isMerchant;
                const traits = npc.unlocked_traits || [];
                const rawDislikes = npc.dislikes || basic.dislikes || [];
                const dislikes = rawDislikes.map(d => typeof d === 'string' ? d : (d.dislike || d.name || ''));
                const rawPreferences = npc.preferences || npc.likes || [];
                
                // Exclude any dislikes or items with negative stances from Likes & Preferences
                const dislikeLowerSet = new Set(dislikes.map(d => d.toLowerCase().trim()));
                const dislikePrefixes = ['dislike', 'dislikes', 'hate', 'hates', 'fear', 'fears', 'avoid', 'avoids', 'detest', 'detests', 'loathe', 'loathes', 'resent', 'resents', 'resist', 'resists', 'disdain', 'disdains', 'repulsed', 'repulses', 'averse'];
                
                const preferences = rawPreferences
                  .map(p => typeof p === 'string' ? p : (p.preference || p.name || ''))
                  .filter(p => {
                    if (!p) return false;
                    const pLow = p.toLowerCase().trim();
                    if (dislikeLowerSet.has(pLow)) return false;
                    const firstWord = pLow.split(/\s+/)[0];
                    if (dislikePrefixes.includes(firstWord)) return false;
                    return true;
                  });
                const memories = npc.intimate_memories || [];
                const appearance = npc.appearance || {};
                const familyTree = npc.family_tree || {};
                const relations = npc.relations || {};
                const infoLevel = npc.info_level ?? 0;
                const skillMod = npc.skill_modifier ?? Math.floor(Math.max(0, score) / 20);
                const rawGender = String(basic.gender || npc.gender || appearance.gender || 'female').toLowerCase();
                const isMale = ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => rawGender.includes(kw)) && !['female', 'woman'].some(kw => rawGender.includes(kw));
                const isNsfwScenario = Boolean(
                  session?.is_nsfw ||
                  npc?.is_nsfw ||
                  (session?.scenario && String(session.scenario).toLowerCase().includes('nsfw')) ||
                  (Array.isArray(session?.scenario_tags) && session.scenario_tags.includes('nsfw'))
                );

                return (
                  <div 
                    key={npc.id || npc.name}
                    className="bg-black/50 border border-fantasy-border/60 hover:border-fantasy-border rounded-lg p-2.5 space-y-1.5 transition-all"
                  >
                    {/* Header */}
                    <div 
                      onClick={() => setExpandedNpc(isExpanded ? null : (npc.id || npc.name))}
                      className="flex items-start justify-between cursor-pointer select-none"
                    >
                      <div className="flex items-center gap-2">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center border font-bold text-xs shrink-0 ${
                          isRomantic 
                            ? 'bg-pink-950/40 border-pink-700/60 text-pink-300' 
                            : 'bg-fantasy-dark border-fantasy-accent/40 text-fantasy-accent'
                        }`}>
                          {isRomantic ? <Heart size={14} /> : <User size={14} />}
                        </div>
                        <div>
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="font-bold text-xs sm:text-sm text-gray-100">{npc.name}</span>
                            {isInParty && (
                              <span className="text-[9px] px-1 py-0.2 bg-purple-950/60 text-purple-300 rounded font-bold uppercase border border-purple-800/40">
                                {t('codex.in_party', 'In Party')}
                              </span>
                            )}
                            {isRomantic && (
                              <span className="text-[9px] px-1 py-0.2 bg-pink-950/60 text-pink-300 rounded font-bold uppercase border border-pink-800/40">
                                {t('codex.romantic', 'Romantic')}
                              </span>
                            )}
                            {npc.clothing_status && (
                              <span className="text-[8.5px] font-mono px-1 py-0.2 rounded bg-black/60 text-gray-300 border border-neutral-700/60 leading-tight">
                                {npc.clothing_status}
                              </span>
                            )}
                          </div>
                          <span className="text-[11px] text-gray-400 font-medium block truncate max-w-56">
                            {basic.role || basic.occupation || (basic.faction ? `${basic.faction} Member` : 'Acquaintance')}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 text-right">
                        <div>
                          <span className={`text-[11px] font-bold block ${tier.color}`}>
                            {tier.label}
                          </span>
                          <span className="font-mono text-[10px] font-semibold text-gray-300">
                            {score > 0 ? `+${score}` : score}
                          </span>
                        </div>
                        {isExpanded ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
                      </div>
                    </div>

                    {/* Active Status Effects */}
                    {Array.isArray(npc.status_effects) && npc.status_effects.filter(s => {
                      const str = typeof s === 'string' ? s.trim() : (s?.name || '').trim();
                      return str && !['[]', '{}', '""', "''", 'none', 'null'].includes(str.toLowerCase());
                    }).length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-0.5">
                        {npc.status_effects
                          .filter(s => {
                            const str = typeof s === 'string' ? s.trim() : (s?.name || '').trim();
                            return str && !['[]', '{}', '""', "''", 'none', 'null'].includes(str.toLowerCase());
                          })
                          .map((eff, i) => (
                            <StatusEffectBadge key={i} effect={eff} />
                          ))}
                      </div>
                    )}

                    {/* Affinity Meter Bar */}
                    <div className="h-1.5 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/40">
                      <div 
                        className={`h-full ${tier.bg} transition-all duration-300`}
                        style={{ width: `${Math.max(5, Math.min(100, ((score + 100) / 400) * 100))}%` }}
                      />
                    </div>

                    {/* Discovered Character Summary: Basic Info & Appearance Badges */}
                    <div className="pt-1.5 space-y-1.5 text-[11px]">
                      {/* Basic Info Badges */}
                      <div className="flex flex-wrap items-center gap-1">
                        {(basic.role || basic.occupation || npc.role) && (
                          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border/50 text-[10.5px]">
                            Role: <strong className="text-gray-100">{basic.role || basic.occupation || npc.role}</strong>
                          </span>
                        )}
                        {(basic.grade || npc.grade) && (
                          <span className="px-1.5 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40 text-[10.5px]">
                            {formatTitle(basic.grade || npc.grade)}
                          </span>
                        )}
                        {(basic.club || npc.club) && (
                          <span className="px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 text-[10.5px]">
                            Club: {formatTitle(basic.club || npc.club)}
                          </span>
                        )}
                        {(basic.race || npc.race) && (
                          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                            {formatRace(basic.race || npc.race)}
                          </span>
                        )}
                        {(basic.gender || npc.gender) && (
                          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                            {formatTitle(basic.gender || npc.gender)}
                          </span>
                        )}
                        {(basic.age || npc.age) && (
                          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                            Age {basic.age || npc.age}
                          </span>
                        )}
                        {(basic.mannerisms || npc.mannerisms) && (
                          <span className="px-1.5 py-0.5 rounded bg-amber-950/30 text-amber-300/90 border border-amber-800/30 text-[10.5px] truncate max-w-full">
                            🎭 {basic.mannerisms || npc.mannerisms}
                          </span>
                        )}
                        {(basic.location || npc.location) && (
                          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/30 text-[10.5px] flex items-center gap-1">
                            <MapPin size={9} className="text-fantasy-accent" />
                            <span>{basic.location || npc.location}</span>
                          </span>
                        )}
                      </div>

                      {/* Appearance Summary Line */}
                      {(() => {
                        const eyeColor = appearance.eye_color || appearance.eyes;
                        const hairColor = appearance.hair_color;
                        const stature = appearance.stature || appearance.height;
                        const physique = appearance.physique;
                        const coatColor = appearance.coat_color || appearance.fur_color || appearance.scale_color || appearance.skin_color;
                        const outfitStyle = appearance.outfit_style || appearance.clothing;
                        const hasAnyApp = Boolean(eyeColor || hairColor || stature || physique || coatColor || outfitStyle);
                        if (!hasAnyApp) return null;
                        return (
                          <div className="text-[10.5px] text-gray-400 bg-black/30 p-1.5 rounded border border-fantasy-border/30 flex flex-wrap gap-x-2 gap-y-0.5">
                            {(stature || physique) && <span>📐 <strong>Build:</strong> {[stature, physique].filter(Boolean).map(formatTitle).join(' • ')}</span>}
                            {eyeColor && <span>👁️ <strong>Eyes:</strong> {formatTitle(eyeColor)}</span>}
                            {hairColor && <span>💇 <strong>Hair:</strong> {formatTitle(hairColor)}</span>}
                            {coatColor && <span>✨ <strong>Skin/Coat:</strong> {formatTitle(coatColor)}</span>}
                            {outfitStyle && <span>👔 <strong>Outfit:</strong> {formatTitle(outfitStyle)}</span>}
                            {isNsfwScenario && (isMale ? appearance.penis_size : appearance.breast_size) && (
                              <span className="text-pink-400/90 font-medium">
                                🔞 {isMale ? `Size: ${appearance.penis_size}` : `Bust: ${appearance.breast_size}`}
                              </span>
                            )}
                          </div>
                        );
                      })()}

                      {/* View Full Profile & Debug Action Buttons */}
                      <div className="flex items-center justify-between pt-1 border-t border-fantasy-border/30 gap-2">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setExpandedNpc(isExpanded ? null : (npc.id || npc.name));
                          }}
                          className="flex items-center gap-1.5 py-1 px-2.5 rounded text-[11px] font-bold border bg-fantasy-accent/10 hover:bg-fantasy-accent/20 border-fantasy-accent/40 text-fantasy-accent transition-all cursor-pointer select-none"
                        >
                          {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                          <span>{isExpanded ? t('codex.view_summary', 'Summary View') : t('codex.view_full_profile', 'View Full Profile')}</span>
                        </button>
                        {isDebugRevealed && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/60 font-mono">
                            {t('codex.debug_revealed_badge', 'DEBUG: Full Profile Revealed')}
                          </span>
                        )}
                        {npc.debug_profile && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              toggleDebugReveal(npc.id || npc.name, isDebugRevealed);
                            }}
                            className="text-[10px] px-2 py-0.5 rounded border border-purple-800/40 bg-purple-950/40 text-purple-300 hover:bg-purple-900/50 transition-all font-mono cursor-pointer select-none"
                          >
                            {isDebugRevealed ? '🔒 Mask' : '🔓 ' + t('codex.debug_reveal', 'Debug Reveal')}
                          </button>
                        )}
                      </div>
                    </div>

                    {/* Expanded Details */}
                    {isExpanded && (
                      <div className="space-y-3 pt-2.5 border-t border-fantasy-border/40 text-xs text-gray-300">
                        
                        {/* Companion In-Party Status & Dismiss Action (Recruitment only occurs via story narrative/dialogue choices) */}
                        {isInParty && (
                          <div className="flex items-center justify-between bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40">
                            <span className="text-xs text-gray-300">
                              {t('codex.in_party_desc', 'Currently traveling in your party.')}
                            </span>
                            <button
                              disabled={companionBusy === npc.name}
                              onClick={(e) => {
                                e.stopPropagation();
                                handleToggleCompanion(npc.name, true);
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold border transition-all shrink-0 bg-red-950/50 border-red-800/60 text-red-300 hover:bg-red-900/60 cursor-pointer"
                            >
                              <UserMinus size={13} />
                              <span>{companionBusy === npc.name ? '...' : t('codex.dismiss', 'Dismiss')}</span>
                            </button>
                          </div>
                        )}

                        {!isDetailedUnlocked ? (
                          <div className="p-4 text-center border border-dashed border-fantasy-border/40 rounded-md bg-black/40 space-y-1">
                            <Lock size={18} className="mx-auto text-amber-400/70" />
                            <p className="text-xs font-semibold text-gray-200">{t('codex.profile_locked', 'Personal Dossier Locked')}</p>
                            <p className="text-[11px] text-gray-400">
                              {t('codex.profile_locked_desc', 'Reach Friend standing (100+ Affinity), recruit them into your party, or speak with them directly to view their full profile.')}
                            </p>
                          </div>
                        ) : (
                          <>
                        {/* Browser / Folder Tabs Header */}
                        <div className="grid grid-cols-4 border-b border-fantasy-border/70 pt-1.5 px-1 bg-black/60 rounded-t-lg gap-1 items-end select-none">
                          {[
                            { id: 'persona', icon: '👤', shortLabel: 'Persona', fullLabel: 'Persona' },
                            { id: 'history', icon: '📜', shortLabel: 'History', fullLabel: 'Shared History' },
                            { id: 'relations', icon: '🌳', shortLabel: 'Relations', fullLabel: 'Relations & Family' },
                            { id: 'intimate', icon: '🔥', shortLabel: 'Intimacy', fullLabel: 'Intimate Dossier' },
                          ].map(t => {
                            const isActive = contactTab === t.id;
                            return (
                              <button
                                key={t.id}
                                type="button"
                                title={t.fullLabel}
                                onClick={(e) => { e.stopPropagation(); setContactTab(t.id); }}
                                className={`min-w-0 py-2 px-1 text-xs font-bold transition-all flex items-center justify-center gap-1 rounded-t-md relative ${
                                  isActive
                                    ? 'bg-black/40 text-fantasy-accent border-t-2 border-t-fantasy-accent border-x border-fantasy-border/70 border-b-black/40 -mb-px z-10 shadow-sm'
                                    : 'bg-black/25 text-gray-400 hover:text-gray-200 hover:bg-black/40 border-t border-x border-transparent border-b border-b-fantasy-border/70'
                                }`}
                              >
                                <span className="text-xs shrink-0">{t.icon}</span>
                                <span className="truncate text-[11px] font-semibold">
                                  <span className="hidden xl:inline">{t.fullLabel}</span>
                                  <span className="xl:hidden">{t.shortLabel}</span>
                                </span>
                              </button>
                            );
                          })}
                        </div>

                        {/* Folder Panel Content Body */}
                        <div className="bg-black/40 border-x border-b border-fantasy-border/70 rounded-b-lg p-3 text-xs -mt-px space-y-3">

                          {/* SUBTAB 1: PERSONA */}
                        {contactTab === 'persona' && (() => {
                          const eyeColor = appearance.eye_color || appearance.eyes;
                          const hairColor = appearance.hair_color;
                          const hairLength = appearance.hair_length;
                          const hairStyle = appearance.hair_style;
                          const coatColor = appearance.coat_color || appearance.fur_color || appearance.scale_color || appearance.feather_color || appearance.coat;
                          const skinColor = appearance.skin_color || appearance.skin;
                          const skinType = appearance.skin_type;
                          const stature = appearance.stature || appearance.height;
                          const physique = appearance.physique;
                          const distinctiveFeatures = appearance.distinctive_features || appearance.features || appearance.marks;
                          const outfitStyle = appearance.outfit_style || appearance.outfit || appearance.clothing;
                          const mannerisms = basic.mannerisms || appearance.mannerisms;

                          const hairParts = [hairLength ? formatTitle(hairLength) : null, hairStyle ? formatTitle(hairStyle) : null].filter(Boolean).join(', ');
                          const hairDesc = hairParts ? (hairColor ? `${hairParts} • ${formatTitle(hairColor)}` : hairParts) : (hairColor ? formatTitle(hairColor) : '');

                          let coatOrSkin = '';
                          if (coatColor) {
                            coatOrSkin = formatTitle(coatColor) + (skinType ? ` (${formatTitle(skinType)})` : '');
                          } else if (skinColor) {
                            coatOrSkin = formatTitle(skinColor) + (skinType ? ` (${formatTitle(skinType)})` : '');
                          } else if (skinType) {
                            coatOrSkin = formatTitle(skinType);
                          }

                          const buildParts = [stature ? formatTitle(stature) : null, physique ? formatTitle(physique) : null].filter(Boolean);
                          const buildDesc = buildParts.join(' • ');
                          const featuresDesc = distinctiveFeatures ? formatTitle(distinctiveFeatures) : '';
                          const outfitDesc = outfitStyle ? formatTitle(outfitStyle) : '';

                          const hasPhysicalAttributes = Boolean(
                            eyeColor || hairDesc || coatOrSkin || buildDesc || featuresDesc || outfitDesc || (isNsfwScenario && (isMale ? (appearance.penis_size || isMale) : (appearance.breast_size || !isMale)))
                          );

                          return (
                            <div className="space-y-2.5">
                              {/* Info Level & Skill Modifier */}
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="text-xs px-2 py-0.5 rounded bg-fantasy-accent/15 text-fantasy-accent border border-fantasy-accent/30 font-mono font-medium">
                                  Info Level: {infoLevel}/3
                                </span>
                                <span className="text-xs px-2 py-0.5 rounded bg-emerald-950/50 text-emerald-300 border border-emerald-700/40 font-mono font-medium">
                                  Skill Modifier: +{skillMod}
                                </span>
                                {basic.race && (
                                  <span className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                                    {formatRace(basic.race)}
                                  </span>
                                )}
                                {basic.gender && (
                                  <span className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                                    {formatTitle(basic.gender)}
                                  </span>
                                )}
                                {basic.age && (
                                  <span className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/50">
                                    Age {basic.age}
                                  </span>
                                )}
                                {basic.grade && (
                                  <span className="text-xs px-2 py-0.5 rounded bg-purple-950/40 text-purple-300 border border-purple-800/40">
                                    {formatTitle(basic.grade)}
                                  </span>
                                )}
                                {basic.club && (
                                  <span className="text-xs px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                    Club: {formatTitle(basic.club)}
                                  </span>
                                )}
                              </div>

                              {/* Physical Appearance & Attributes */}
                              {hasPhysicalAttributes && (() => {
                                const hasVitals = Boolean(
                                  eyeColor || buildDesc || (isNsfwScenario && (isMale ? (appearance.penis_size || isMale) : (appearance.breast_size || !isMale)))
                                );
                                const hasDetails = Boolean(hairDesc || coatOrSkin || featuresDesc || outfitDesc);

                                return (
                                  <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs space-y-2.5">
                                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block flex items-center gap-1.5">
                                      ✨ Physical Appearance
                                    </span>

                                    {/* Quick Vitals Badges Bar */}
                                    {hasVitals && (
                                      <div className={`flex flex-wrap items-center gap-1.5 ${hasDetails ? 'pb-2 border-b border-fantasy-border/25' : ''}`}>
                                        {eyeColor && (
                                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-black/60 border border-fantasy-border/50 text-gray-300">
                                            <span className="text-gray-400">👁️ Eyes:</span>
                                            <strong className="text-gray-100 font-medium">{formatTitle(eyeColor)}</strong>
                                          </span>
                                        )}
                                        {buildDesc && (
                                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-black/60 border border-fantasy-border/50 text-gray-300">
                                            <span className="text-gray-400">📏 Build:</span>
                                            <strong className="text-gray-100 font-medium">{buildDesc}</strong>
                                          </span>
                                        )}
                                        {isNsfwScenario && !isMale && (
                                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-pink-950/40 border border-pink-800/50 text-pink-300">
                                            <span className="text-pink-400 font-medium">🔞 Breast Size:</span>
                                            <strong className="text-pink-100 font-medium">
                                              {formatTitle(appearance.breast_size || 'Modest B-Cup')}
                                            </strong>
                                            {appearance.asset_texture && (
                                              <span className="text-pink-200 text-[10px] italic font-normal">({appearance.asset_texture})</span>
                                            )}
                                          </span>
                                        )}
                                        {isNsfwScenario && isMale && (
                                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-950/40 border border-purple-800/50 text-purple-300">
                                            <span className="text-purple-400 font-medium">🔞 Penis Size:</span>
                                            <strong className="text-purple-100 font-medium">
                                              {formatTitle(appearance.penis_size || 'Average')}
                                            </strong>
                                            {appearance.asset_texture && (
                                              <span className="text-purple-200 text-[10px] italic font-normal">({appearance.asset_texture})</span>
                                            )}
                                          </span>
                                        )}
                                      </div>
                                    )}

                                    {/* Descriptive Physical Attributes (Full Width, Balanced Spacing) */}
                                    {hasDetails && (
                                      <div className="space-y-1.5 text-gray-300">
                                        {hairDesc && (
                                          <div className="leading-snug">
                                            <span className="text-gray-400 font-medium">💇 Hair: </span>
                                            <strong className="text-gray-200 font-medium">{hairDesc}</strong>
                                          </div>
                                        )}
                                        {coatOrSkin && (
                                          <div className="leading-snug">
                                            <span className="text-gray-400 font-medium">🐾 Coat / Skin: </span>
                                            <strong className="text-gray-200 font-medium">{coatOrSkin}</strong>
                                          </div>
                                        )}
                                        {featuresDesc && (
                                          <div className="leading-snug">
                                            <span className="text-gray-400 font-medium">✨ Features: </span>
                                            <strong className="text-gray-200 font-medium">{featuresDesc}</strong>
                                          </div>
                                        )}
                                        {outfitDesc && (
                                          <div className="leading-snug">
                                            <span className="text-gray-400 font-medium">👔 Outfit: </span>
                                            <span className="text-gray-300">{outfitDesc}</span>
                                          </div>
                                        )}
                                      </div>
                                    )}
                                  </div>
                                );
                              })()}

                              {/* Mannerisms */}
                              {mannerisms && (
                                <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                    🎭 Mannerisms
                                  </span>
                                  {mannerisms}
                                </div>
                              )}

                              {/* Background Description & Notes */}
                              {(basic.description || appearance.summary || npc.description) && (
                                <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                    📖 Background & Notes
                                  </span>
                                  {basic.description || appearance.summary || npc.description}
                                </div>
                              )}

                              {/* Unlocked Traits */}
                              {traits.length > 0 && (
                                <div>
                                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                    Known Traits
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {traits.map((t, idx) => (
                                      <span key={idx} className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border">
                                        {typeof t === 'string' ? t : (t.trait || t.name)}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Likes / Preferences */}
                              {preferences.length > 0 && (
                                <div>
                                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                    Likes & Preferences
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {preferences.map((p, idx) => (
                                      <span key={idx} className="text-xs px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                        {typeof p === 'string' ? p : (p.preference || p.name)}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}

                              {/* Dislikes */}
                              {dislikes.length > 0 && (
                                <div>
                                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                    Dislikes & Pet Peeves
                                  </span>
                                  <div className="flex flex-wrap gap-1.5">
                                    {dislikes.map((d, idx) => (
                                      <span key={idx} className="text-xs px-2 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40">
                                        {typeof d === 'string' ? d : (d.dislike || d.name)}
                                      </span>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                          );
                        })()}

                        {/* SUBTAB: SHARED HISTORY */}
                        {contactTab === 'history' && (() => {
                          const recentMemories = Array.isArray(npc.recent_memories)
                            ? npc.recent_memories
                            : (Array.isArray(npc.rel_history) ? npc.rel_history : []);

                          return (
                            <div className="space-y-3">
                              <div className="flex items-center justify-between border-b border-fantasy-border/30 pb-2">
                                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider flex items-center gap-1.5">
                                  <Scroll size={13} />
                                  <span>Recent Shared Interactions & History</span>
                                </span>
                                <span className="text-[10px] px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/40 font-mono">
                                  {recentMemories.length} {recentMemories.length === 1 ? 'Event' : 'Events'}
                                </span>
                              </div>

                              {recentMemories.length === 0 ? (
                                <div className="py-6 text-center text-gray-500 italic">
                                  No shared interactions recorded yet. Spend time with {npc.name || 'this character'} to build your shared history.
                                </div>
                              ) : (
                                <div className="space-y-2">
                                  {recentMemories.map((mem, idx) => {
                                    const text = typeof mem === 'string' ? mem : (mem.memory_fact || mem.summary || JSON.stringify(mem));
                                    return (
                                      <div
                                        key={idx}
                                        className="flex items-start gap-2.5 p-2 rounded bg-black/50 border border-fantasy-border/30 hover:border-amber-500/40 transition-colors"
                                      >
                                        <span className="mt-0.5 text-amber-400 font-mono text-[10px] bg-amber-950/40 px-1.5 py-0.5 rounded border border-amber-800/40 shrink-0">
                                          #{recentMemories.length - idx}
                                        </span>
                                        <div className="text-gray-200 leading-relaxed text-xs">
                                          {text}
                                        </div>
                                      </div>
                                    );
                                  })}
                                </div>
                              )}
                            </div>
                          );
                        })()}

                        {/* SUBTAB 2: RELATIONS & FAMILY */}
                        {contactTab === 'relations' && (() => {
                          const disRel = npc.disclosed_relations || {};
                          const romData = disRel.romance || relations.romance || {};
                          const famData = disRel.family || {};
                          const friendsList = disRel.friends?.members || relations.friends || [];
                          const rivalsList = disRel.rivals?.members || relations.rivals || [];

                          return (
                            <div className="space-y-3">
                              {/* 1. Immediate Family Tree */}
                              <div>
                                <span className="text-xs font-bold text-fantasy-accent uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  👨‍👩‍👧‍👦 Immediate Family Tree
                                </span>
                                {famData.members && famData.members.length > 0 ? (
                                  <div className="space-y-1.5">
                                    {famData.members.map((mem, i) => {
                                      const rel = mem.relation || 'Relative';
                                      const rEmoji = rel.includes('Father') ? '👨' : rel.includes('Mother') ? '👩' : rel.includes('Brother') ? '👦' : rel.includes('Sister') ? '👧' : '👤';
                                      const statusDot = (mem.status || 'Alive').toLowerCase() === 'alive' ? '🟢' : '💀';
                                      const isParent = rel.includes('Father') || rel.includes('Mother') || rel.includes('Parent');
                                      return (
                                        <div key={i} className="text-gray-300 leading-snug">
                                          • {rEmoji} <strong>{rel}</strong>: {mem.name} {mem.race ? `(${formatRace(mem.race)})` : ''} — {statusDot} {(!isParent && (mem.occupation || mem.grade)) ? <span className="italic text-gray-400">— {mem.occupation || mem.grade}</span> : (mem.occupation ? <span className="italic text-gray-400">— {mem.occupation}</span> : '')}
                                        </div>
                                      );
                                    })}
                                  </div>
                                ) : famData.locked_message ? (
                                  <p className="text-gray-400 italic text-xs leading-relaxed">{famData.locked_message}</p>
                                ) : (familyTree.parents?.length > 0 || familyTree.siblings?.length > 0 || (Array.isArray(familyTree) && familyTree.length > 0)) ? (
                                  <div className="space-y-1.5">
                                    {Array.isArray(familyTree) ? (
                                      familyTree.map((mem, i) => (
                                        <div key={i} className="text-gray-300 leading-snug">
                                          • <strong>{mem.name || mem}</strong> {mem.relation ? `(${mem.relation})` : ''} {mem.occupation ? `— ${mem.occupation}` : ''}
                                        </div>
                                      ))
                                    ) : (
                                      <>
                                        {familyTree.parents?.map((p, i) => (
                                          <div key={`p-${i}`} className="text-gray-300 leading-snug">
                                            • Parent: <strong>{typeof p === 'string' ? p : p.name}</strong> {p.occupation ? `(${p.occupation})` : ''} {p.status ? `[${p.status}]` : ''}
                                          </div>
                                        ))}
                                        {familyTree.siblings?.map((s, i) => (
                                          <div key={`s-${i}`} className="text-gray-300 leading-snug">
                                            • Sibling: <strong>{typeof s === 'string' ? s : s.name}</strong> {s.occupation || s.grade ? `(${s.occupation || s.grade})` : ''} {s.status ? `[${s.status}]` : ''}
                                          </div>
                                        ))}
                                      </>
                                    )}
                                  </div>
                                ) : (
                                  <p className="text-gray-500 italic text-xs">No family records uncovered yet.</p>
                                )}
                              </div>

                              {/* 2. Romantic Standing */}
                              <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block">
                                  💖 Romantic Standing
                                </span>
                                <div className="space-y-1 leading-relaxed">
                                  <div>
                                    • <strong className="text-gray-200">Current Status</strong>:{' '}
                                    {romData.current_partner ? (
                                      <span className="text-pink-300 font-semibold">
                                        💖 {formatPersonEntity(romData.current_partner)}
                                      </span>
                                    ) : (
                                      <span className="text-gray-300 font-medium">
                                        {romData.status || (relations.current_partner ? 'In a Relationship' : 'Single')}
                                      </span>
                                    )}
                                  </div>

                                  {romData.secret_partner && (
                                    <div>
                                      • <strong className="text-gray-200">Secret Affair</strong>:{' '}
                                      {romData.secret_partner.locked ? (
                                        <span className="text-gray-500 italic">{romData.secret_partner.message}</span>
                                      ) : (
                                        <span className="text-rose-400 font-semibold">
                                          🤫 {formatPersonEntity(romData.secret_partner)}
                                        </span>
                                      )}
                                    </div>
                                  )}

                                  <div>
                                    • <strong className="text-gray-200">Past Ex-Partner(s)</strong>:{' '}
                                    {romData.ex_partners && romData.ex_partners.length > 0 ? (
                                      <span className="text-gray-300">
                                        💔 {romData.ex_partners.map(p => typeof p === 'object' && p.locked ? p.message : formatPersonEntity(p)).filter(Boolean).join(', ')}
                                      </span>
                                    ) : (romData.revealed || infoLevel >= 2 || isDebugRevealed) ? (
                                      <span className="text-gray-400 italic">None (No prior romantic partners)</span>
                                    ) : (
                                      <span className="text-gray-500 italic">🔒 Locked (Requires Info Level 2+)</span>
                                    )}
                                  </div>
                                </div>
                              </div>

                              {/* 3. Friends */}
                              <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                                <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider block">
                                  🤝 Friends
                                </span>
                                {friendsList.length > 0 ? (
                                  <div className="space-y-1">
                                    {friendsList.map((f, i) => (
                                      <div key={i} className="text-cyan-300 font-medium">
                                        • 🤝 {formatPersonEntity(f)}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-gray-500 italic text-xs">No close friends recorded.</p>
                                )}
                              </div>

                              {/* 4. Rivals */}
                              <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block">
                                  ⚔️ Rivals
                                </span>
                                {rivalsList.length > 0 ? (
                                  <div className="space-y-1">
                                    {rivalsList.map((r, i) => (
                                      <div key={i} className="text-amber-300 font-medium">
                                        • ⚔️ {formatPersonEntity(r)}
                                      </div>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-gray-500 italic text-xs">No known rivals recorded.</p>
                                )}
                              </div>

                              {/* Footer Disclosure Level */}
                              <div className="text-[11px] text-gray-500 font-mono pt-1.5 border-t border-fantasy-border/20">
                                Information Disclosure Level: {infoLevel}/3 • Social Graph & Lineage Dossier{isDebugRevealed ? ' • [🛠️ DEBUG: Revealed]' : ''}
                              </div>
                            </div>
                          );
                        })()}

                        {/* SUBTAB 3: INTIMATE & HISTORY */}
                        {contactTab === 'intimate' && (() => {
                          const intSec = npc.intimate_sections || {};
                          const hasSections = Boolean(intSec.anatomy && intSec.dynamic);

                          // Fallback data if intimate_sections not provided
                          const rawGen = (basic.gender || npc.gender || '').toLowerCase();
                          const isMale = ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => rawGen.includes(kw)) && !['female', 'woman', 'girl', 'lady'].some(kw => rawGen.includes(kw));
                          const bSize = (appearance.breast_size || 'Modest B-Cup');
                          const bTitle = bSize.charAt(0).toUpperCase() + bSize.slice(1);
                          const pSize = (appearance.penis_size || 'Average');
                          const pTitle = pSize.charAt(0).toUpperCase() + pSize.slice(1);
                          const sizeDisplay = isMale ? ((infoLevel >= 3 || isDebugRevealed) ? pTitle : 'Unknown') : bTitle;

                          const iExpDisp = (appearance.experience && appearance.experience.toLowerCase() !== 'unknown') ? appearance.experience : (infoLevel >= 3 || isDebugRevealed ? (appearance.intercourse_experience === 'virgin' ? 'Virgin' : 'Non-Virgin') : 'Unknown');
                          const oExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.oral_experience || 'Inexperienced') : 'Unknown';
                          const mExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.manual_experience || 'Inexperienced') : 'Unknown';
                          const aExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.anal_experience || 'Inexperienced') : 'Unknown';

                          const underObj = typeof appearance.undergarments === 'object' && appearance.undergarments !== null ? appearance.undergarments : {};
                          const rawBra = underObj.bra || appearance.bra || (typeof appearance.undergarments === 'string' && appearance.undergarments.includes('Bra:') ? appearance.undergarments.split('•')[0]?.replace('Bra:', '').trim() : '');
                          const rawUnd = underObj.underwear || appearance.underwear || (typeof appearance.undergarments === 'string' && appearance.undergarments.includes('Underwear:') ? appearance.undergarments.split('•')[1]?.replace('Underwear:', '').trim() : (typeof appearance.undergarments === 'string' ? appearance.undergarments : ''));
                          const braVal = rawBra ? rawBra.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone') : '';
                          const undVal = rawUnd ? rawUnd.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone') : '';

                          const isHistoryUnlocked = infoLevel >= 2 || npc.intimate_revealed || npc.history_revealed || isDebugRevealed;
                          const hasHistoryEntries = Boolean(npc.past_intimate_history || (npc.past_intimate_entries && npc.past_intimate_entries.length > 0));
                          const ROMANTIC_KEYWORDS = [
                            'kiss', 'confess', 'date', 'intercourse', 'oral', 'manual', 'anal', 'virgin',
                            'intimate', 'bedroom', 'made love', 'make love', 'slept together',
                            'affectionate', 'tender', 'romantic', 'romance', 'caress', 'embrace', 'cuddle',
                            'passionate', 'passion'
                          ];
                          const isRomanticMilestone = (m) => {
                            if (!m) return false;
                            const s = String(typeof m === 'string' ? m : (m.summary || m.event || '')).toLowerCase();
                            if (s.startsWith('past history:')) return false;
                            if (s.includes('[romance]') || s.includes('[intimate]')) return true;
                            return ROMANTIC_KEYWORDS.some(kw => s.includes(kw));
                          };
                          const sharedMilestones = (npc.shared_romantic_milestones && npc.shared_romantic_milestones.length > 0)
                            ? npc.shared_romantic_milestones
                            : memories.filter(isRomanticMilestone);

                          return (
                            <div className="space-y-3">
                              {/* 1. Anatomy & Experience */}
                              <div>
                                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  🔞 Anatomy & Experience
                                </span>
                                {hasSections && intSec.anatomy ? (
                                  renderBulletPoints(intSec.anatomy.map(line => {
                                    if (!isMale && /breast size.*unknown/i.test(line) && bTitle) {
                                      return `• **Breast Size**: ${bTitle}`;
                                    }
                                    return line;
                                  }))
                                ) : (
                                    <div className="space-y-1 text-gray-300 leading-relaxed">
                                      <div>• <strong className="text-gray-100">{isMale ? 'Penis Size' : 'Breast Size'}</strong>: {sizeDisplay}</div>
                                      {appearance.asset_texture && (
                                        <div>• <strong className="text-gray-100">Tactile Feature</strong>: <span className="text-pink-300 font-medium">{appearance.asset_texture}</span></div>
                                      )}
                                      <div>• <strong className="text-gray-100">Intercourse</strong>: {iExpDisp}</div>
                                      <div>• <strong className="text-gray-100">Oral Intimacy</strong>: {oExpDisp}</div>
                                      <div>• <strong className="text-gray-100">Manual Intimacy</strong>: {mExpDisp}</div>
                                      <div>• <strong className="text-gray-100">Anal Intimacy</strong>: {aExpDisp}</div>
                                    </div>
                                )}
                              </div>

                              {/* 2. Demeanor & Dynamic */}
                              <div className="pt-2 border-t border-fantasy-border/30">
                                <span className="text-xs font-bold text-purple-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  🎭 Demeanor & Dynamic
                                </span>
                                {hasSections && intSec.dynamic ? (
                                  renderBulletPoints(intSec.dynamic)
                                ) : (
                                  <div className="space-y-1 text-gray-300 leading-relaxed">
                                    <div>• <strong className="text-gray-100">Demeanor</strong>: {(infoLevel >= 3 || isDebugRevealed) && appearance.intimate_demeanor ? appearance.intimate_demeanor : <span className="text-gray-500 italic">Unknown</span>}</div>
                                    <div>• <strong className="text-gray-100">Dynamic</strong>: {(infoLevel >= 3 || isDebugRevealed) && appearance.intimate_dynamic ? appearance.intimate_dynamic : <span className="text-gray-500 italic">Unknown</span>}</div>
                                    <div>• <strong className="text-gray-100">Openness</strong>: {(infoLevel >= 3 || isDebugRevealed) && (appearance.erotic_openness || appearance.openness) ? (appearance.erotic_openness || appearance.openness) : <span className="text-gray-500 italic">Unknown</span>}</div>
                                  </div>
                                )}
                              </div>

                              {/* 3. Undergarments */}
                              <div className="pt-2 border-t border-fantasy-border/30">
                                <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  🩲 Undergarments
                                </span>
                                {hasSections && intSec.undergarments ? (
                                  renderBulletPoints(intSec.undergarments)
                                ) : (
                                  <div className="space-y-1 text-gray-300 leading-relaxed">
                                    {!isMale && (
                                      <div>• <strong className="text-gray-100">Bra</strong>: {(infoLevel >= 3 || isDebugRevealed) && braVal ? braVal : <span className="text-gray-500 italic">Unknown</span>}</div>
                                    )}
                                    <div>• <strong className="text-gray-100">Underwear</strong>: {(infoLevel >= 3 || isDebugRevealed) && undVal ? undVal : <span className="text-gray-500 italic">Unknown</span>}</div>
                                  </div>
                                )}
                              </div>

                              {/* 4. Sensitive Spots */}
                              <div className="pt-2 border-t border-fantasy-border/30">
                                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  🌸 Sensitive Spots
                                </span>
                                {hasSections && (intSec.sensitive_spots || intSec.sensitivities) ? (
                                  renderBulletPoints(intSec.sensitive_spots || intSec.sensitivities.filter(s => s.toLowerCase().includes('sensitive spot')))
                                ) : (
                                  <div className="space-y-1 text-gray-300 leading-relaxed">
                                    <div>• <strong className="text-gray-100">Sensitive Spots</strong>: {(infoLevel >= 3 || isDebugRevealed) && appearance.sensitive_spots ? appearance.sensitive_spots : <span className="text-gray-500 italic">Unknown</span>}</div>
                                  </div>
                                )}
                              </div>

                              {/* 5. Desires & Turn-Offs */}
                              <div className="pt-2 border-t border-fantasy-border/30">
                                <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  🔥 Desires & Turn-Offs
                                </span>
                                {hasSections && (intSec.desires_and_turn_offs || intSec.sensitivities) ? (
                                  renderBulletPoints(intSec.desires_and_turn_offs || intSec.sensitivities.filter(s => !s.toLowerCase().includes('sensitive spot')))
                                ) : (
                                  <div className="space-y-1 text-gray-300 leading-relaxed">
                                    <div>• <strong className="text-gray-100">Desires & Kinks</strong>: {(infoLevel >= 3 || isDebugRevealed) && (appearance.desires_and_kinks || appearance.turn_ons) ? (Array.isArray(appearance.desires_and_kinks || appearance.turn_ons) ? (appearance.desires_and_kinks || appearance.turn_ons).join(', ') : (appearance.desires_and_kinks || appearance.turn_ons)) : <span className="text-gray-500 italic">Unknown</span>}</div>
                                    <div>• <strong className="text-red-300">Turn-Offs</strong>: {(infoLevel >= 3 || isDebugRevealed) && appearance.turn_offs ? (Array.isArray(appearance.turn_offs) ? appearance.turn_offs.join(', ') : appearance.turn_offs) : <span className="text-gray-500 italic">Unknown</span>}</div>
                                  </div>
                                )}
                              </div>

                              {/* 5. Act & Position Preferences */}
                              <div className="pt-2 border-t border-fantasy-border/30">
                                <span className="text-xs font-bold text-rose-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                  ❤️ Act & Position Preferences
                                </span>
                                {hasSections && intSec.act_preferences ? (
                                  renderBulletPoints(intSec.act_preferences)
                                ) : (
                                  <div className="space-y-1 text-gray-300 leading-relaxed">
                                    <div>• <strong className="text-gray-100">Preferred / Likes</strong>: {(infoLevel >= 3 || isDebugRevealed) && (appearance.favorite_acts || appearance.act_likes) ? (Array.isArray(appearance.favorite_acts) ? appearance.favorite_acts.join(', ') : (appearance.act_likes || 'None')) : <span className="text-gray-500 italic">Unknown</span>}</div>
                                    <div>• <strong className="text-gray-100">Aversions / Dislikes</strong>: {(infoLevel >= 3 || isDebugRevealed) && (appearance.disliked_acts || appearance.act_dislikes) ? (Array.isArray(appearance.disliked_acts) ? appearance.disliked_acts.join(', ') : (appearance.act_dislikes || 'None')) : <span className="text-gray-500 italic">Unknown</span>}</div>
                                  </div>
                                )}
                              </div>

                              {/* 6. Past Intimate History */}
                              <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                                <span className="text-xs font-bold text-gray-300 uppercase tracking-wider block mb-0.5">
                                  Past Intimate History
                                </span>
                                {!isHistoryUnlocked ? (
                                  <p className="text-gray-500 italic text-xs leading-relaxed">
                                    🔒 Locked — Requires deeper personal bond (Friend+ / Info Level 2+) to uncover.
                                  </p>
                                ) : hasHistoryEntries ? (
                                  npc.past_intimate_entries && npc.past_intimate_entries.length > 0 ? (
                                    <div className="space-y-1">
                                      {npc.past_intimate_entries.map((h, i) => (
                                        <p key={i} className="text-gray-300 italic text-xs leading-relaxed">• {h}</p>
                                      ))}
                                    </div>
                                  ) : Array.isArray(npc.past_intimate_history) ? (
                                    <div className="space-y-1">
                                      {npc.past_intimate_history.map((h, i) => (
                                        <p key={i} className="text-gray-300 italic text-xs leading-relaxed">• {h}</p>
                                      ))}
                                    </div>
                                  ) : (
                                    <p className="text-gray-300 italic text-xs leading-relaxed">• {npc.past_intimate_history}</p>
                                  )
                                ) : (
                                  <p className="text-gray-400 italic text-xs leading-relaxed">• Virgin (No prior intimate history before meeting you)</p>
                                )}
                              </div>

                              {/* 7. Shared Romantic Milestones */}
                              <div className="pt-2 border-t border-fantasy-border/30">
                                <span className="text-xs font-bold text-pink-400 uppercase tracking-wider flex items-center gap-1.5 mb-1.5">
                                  <Sparkles size={12} />
                                  <span>Shared Romantic Milestones</span>
                                </span>
                                {sharedMilestones.length > 0 ? (
                                  <div className="space-y-1.5 bg-black/50 p-2.5 rounded-lg border border-pink-900/40">
                                    {sharedMilestones.map((m, idx) => (
                                      <p key={idx} className="text-xs text-pink-200/90 leading-relaxed italic">
                                        • {typeof m === 'string' ? m : (m.summary || m.event)}
                                      </p>
                                    ))}
                                  </div>
                                ) : (
                                  <p className="text-gray-500 italic text-xs leading-relaxed">
                                    *No romantic milestones shared with this character yet.*
                                  </p>
                                )}
                              </div>

                              {/* Footer Disclosure Level */}
                              <div className="text-[11px] text-gray-500 font-mono pt-1.5 border-t border-fantasy-border/20">
                                Information Disclosure Level: {infoLevel}/3 • Intimate Dossier{isDebugRevealed ? ' • [🛠️ DEBUG: Revealed]' : ''}
                              </div>
                            </div>
                          );
                        })()}
                        </div>
                        </>
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
                <p className="text-xs">{t('codex.factions_empty', 'No factions discovered yet.')}</p>
              </div>
            ) : (
              filteredFactions.map(faction => {
                const fid = faction.faction_id || faction.name;
                const rep = faction.reputation ?? faction.reputation_score ?? 0;
                const repTier = getReputationTier(rep, t);
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
                              Rank {playerRank || 1} {faction.player_title ? `• ${faction.player_title}` : t('codex.member', 'Member')}
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
                                  ✨ {t('codex.active_faction_perks', 'Active Faction Perks')}
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
                                  ⚔️ {t('codex.rival_factions', 'Rival Factions')}
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
                                <span>{t('codex.leadership_hierarchy', 'Leadership Hierarchy')}</span>
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
                                        {t('codex.holder', 'Holder')}: <strong className="text-gray-200">{slot.is_vacant ? t('codex.vacant', 'Vacant') : slot.name}</strong>
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
                            {t('codex.faction_hq_ops', 'Faction Headquarters Operations')}
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
                              <span>{isMember ? t('codex.leave_faction', 'Leave Faction') : t('codex.join_faction', 'Pledge / Join')}</span>
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
                              <span>{t('codex.safehouse_rest', 'Safehouse Rest')}</span>
                            </button>

                            {/* Quartermaster Shop */}
                            <button
                              disabled={Boolean(factionBusy)}
                              onClick={() => handleFactionOp(faction.faction_id, 'quartermaster')}
                              className="flex items-center justify-center gap-1.5 py-1.5 px-2 rounded text-[11px] font-bold border bg-amber-950/40 hover:bg-amber-900/50 border-amber-700/60 text-amber-300 transition-all"
                            >
                              <ShoppingBag size={12} />
                              <span>{t('codex.quartermaster', 'Quartermaster')}</span>
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


          {/* 3. WORLD LORE TAB (strictly world events, places, factions, artifacts, history) */}
          {subTab === 'lore' && (
            <div className="space-y-2.5">
              {filteredLore.length === 0 ? (
                <div className="text-center py-8 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
                  <Globe size={24} className="mx-auto mb-1.5 opacity-40" />
                  <p className="text-xs">{t('codex.no_lore', 'No world details documented yet.')}</p>
                  <p className="text-[10px] text-gray-500 mt-1">Discover world events, locations, artifacts, and historical lore as your adventure unfolds.</p>
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

          {/* SUBTAB 4: AGENDA & COMMITMENTS */}
          {subTab === 'agenda' && (
            <div className="space-y-3 pb-8">
              {filteredCommitments.length === 0 ? (
                <div className="text-center py-10 text-gray-500 border border-dashed border-fantasy-border/50 rounded-lg">
                  <Calendar size={28} className="mx-auto mb-2 opacity-40 text-fantasy-accent" />
                  <p className="text-xs font-medium text-gray-400">{t('codex.no_agenda', 'No Active Obligations or Rendezvous')}</p>
                  <p className="text-[10px] text-gray-500 mt-1 max-w-[220px] mx-auto leading-relaxed">
                    Promises, debts, pacts, and scheduled meetups will appear here as you make commitments with entities in the world.
                  </p>
                </div>
              ) : (
                filteredCommitments.map((c, idx) => {
                  const isRendezvous = c.commitment_type === 'rendezvous';
                  const isArrived = c.status === 'arrived';
                  const isFulfilled = c.status === 'fulfilled';
                  const isFlaked = c.status === 'flaked';
                  const isConfidential = Boolean(c.is_confidential);
                  const shortLoc = (c.target_location || c.rendezvous_location || '').split('➔').pop().trim();
                  const targetName = c.target_entity || c.npc_name || 'Counterparty';

                  const hasOverlapConflict = isRendezvous && filteredCommitments.some(other => {
                    if (!other || (other.id && other.id === c.id) || (other.commitment_key && other.commitment_key === c.commitment_key) || other.commitment_type !== 'rendezvous') return false;
                    const sameDay = (other.scheduled_day || 1) === (c.scheduled_day || 1);
                    if (!sameDay) return false;
                    const oStart = other.start_minute ?? 0;
                    const oEnd = other.end_minute ?? 1439;
                    const cStart = c.start_minute ?? 0;
                    const cEnd = c.end_minute ?? 1439;
                    return Math.max(oStart, cStart) < Math.min(oEnd, cEnd);
                  });

                  return (
                    <div
                      key={c.id || c.commitment_key || idx}
                      className={`p-3.5 rounded-lg border transition-all ${
                        isArrived
                          ? 'bg-emerald-950/20 border-emerald-500/40 shadow-sm shadow-emerald-950/40'
                          : isFulfilled
                          ? 'bg-black/30 border-gray-800 opacity-70'
                          : isFlaked
                          ? 'bg-rose-950/20 border-rose-800/40'
                          : 'bg-black/50 border-fantasy-border/60 hover:border-fantasy-accent/40'
                      }`}
                    >
                      <div className="flex justify-between items-start gap-1.5">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          {isRendezvous ? (
                            <Calendar size={13} className="text-fantasy-accent shrink-0" />
                          ) : (
                            <Scroll size={13} className="text-amber-400 shrink-0" />
                          )}
                          <h5 className="font-semibold text-xs text-gray-100">
                            {c.title || (isRendezvous ? `Meetup with ${targetName}` : `Promise to ${targetName}`)}
                          </h5>
                          {hasOverlapConflict && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                              ⚠️ Overlap
                            </span>
                          )}
                        </div>

                        <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono uppercase font-bold border ${
                          isArrived
                            ? 'bg-emerald-950/60 text-emerald-300 border-emerald-700/50'
                            : isFulfilled
                            ? 'bg-neutral-800 text-gray-400 border-neutral-700'
                            : isFlaked
                            ? 'bg-rose-950/60 text-rose-300 border-rose-800/50'
                            : 'bg-fantasy-accent/10 text-fantasy-accent border-fantasy-accent/30'
                        }`}>
                          {c.status || 'Active'}
                        </span>
                      </div>

                      <p className="text-[11px] text-gray-300 leading-snug mt-1.5">
                        {c.description || c.topic || 'No details provided.'}
                      </p>

                      <div className="flex flex-wrap items-center justify-between text-[10px] text-gray-400 pt-2 mt-2 border-t border-fantasy-border/30 gap-1">
                        <div className="flex items-center gap-2">
                          <span>👤 <strong>{targetName}</strong></span>
                          {isConfidential && (
                            <span className="text-[9px] px-1 py-0.2 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
                              Confidential
                            </span>
                          )}
                        </div>

                        {shortLoc && (
                          <span className="flex items-center gap-1 text-gray-400">
                            <MapPin size={10} className="text-fantasy-accent" />
                            <span>{shortLoc}</span>
                          </span>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}

        </div>
      )}

    </div>
  );
};

export default CodexPanel;
