import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  BookOpen, Users, Flag, Globe, Heart, Shield, 
  Sparkles, Search, MessageCircle, MapPin, ChevronDown, ChevronRight, User, UserMinus,
  Crown, ShoppingBag, Swords, BedDouble, Lock, Scroll, Calendar, Clock, Smartphone
} from 'lucide-react';
import { StatusEffectBadge } from './CharacterSheet';
import { formatCleanLocation, cleanProseLocations } from '../../utils/locationFormat';

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

const DEBUG_DOSSIER_TABS = [
  { id: 'persona', icon: '👤', shortLabel: 'Persona', fullLabel: 'Persona & Appearance' },
  { id: 'history', icon: '📜', shortLabel: 'History', fullLabel: 'History & Schedule' },
  { id: 'relations', icon: '🌳', shortLabel: 'Relations', fullLabel: 'Relations & Family' },
  { id: 'intimate', icon: '🔥', shortLabel: 'Intimacy', fullLabel: 'Intimate Dossier' },
];

const CodexPanel = ({
  codexHook,
  session,
  user,
  onSessionUpdated,
  onRefreshCharacter,
  onOpenMerchant,
  onTriggerAction,
  targetContactName,
  targetContactPulse,
  onJumpToSavedContact,
}) => {
  const { t } = useTranslation();
  const { contacts, factions, lorebook, commitments = [], loading, factionHqAction, refreshCodex, cancelCommitment } = codexHook;
  const [subTab, setSubTab] = useState('contacts'); // 'contacts' | 'factions' | 'lore'
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNpc, setExpandedNpc] = useState(null);
  const [highlightedNpcKey, setHighlightedNpcKey] = useState(null);
  const [debugDossierTab, setDebugDossierTab] = useState('persona');
  const [expandedFaction, setExpandedFaction] = useState(null);
  const [loreFilter, setLoreFilter] = useState('all'); // 'all' | 'commitments'
  const [companionBusy, setCompanionBusy] = useState(null);
  const [factionBusy, setFactionBusy] = useState(null);
  const [cancellingCommitmentId, setCancellingCommitmentId] = useState(null);
  const [companionFeedback, setCompanionFeedback] = useState(null);
  const cardRefs = useRef({});

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
    const list = contacts
      .filter(c => !c.is_dispatch_channel && c.is_discovered !== false)
      .map(c => ({ ...c, is_contact: true }));
    const seen = new Set(list.map(c => (c.name || '').toLowerCase().trim()));

    const personEntities = (lorebook.entities || []).filter(e => e.entity_type === 'person');
    personEntities.forEach(p => {
      const pName = (p.name || '').toLowerCase().trim();
      const hasMet = p.is_discovered !== false && Boolean(
        p.is_discovered ||
        p.relationship_score ||
        p.affinity ||
        p.last_in_person_ts
      );
      if (pName && !seen.has(pName) && hasMet) {
        seen.add(pName);
        list.push({
          ...p,
          id: p.id || p.npc_id || p.name,
          is_contact: Boolean(p.is_contact),
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

  useEffect(() => {
    if (targetContactName) {
      setSubTab('contacts');
      setSearchQuery('');
      const targetLow = String(targetContactName ?? '').trim().toLowerCase();
      const matched = knownCharacters.find(c =>
        String(c.name ?? '').trim().toLowerCase() === targetLow ||
        String(c.id ?? '').trim().toLowerCase() === targetLow ||
        String(c.npc_id ?? '').trim().toLowerCase() === targetLow
      );
      const key = matched ? (matched.id || matched.name) : targetContactName;
      setExpandedNpc(key);
      setHighlightedNpcKey(key);
      const timer = setTimeout(() => {
        const el = cardRefs.current[key] || (matched?.name && cardRefs.current[String(matched.name).toLowerCase()]) || cardRefs.current[targetLow];
        if (el && typeof el.scrollIntoView === 'function') {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 80);
      const clearTimer = setTimeout(() => setHighlightedNpcKey(null), 2400);
      return () => {
        clearTimeout(timer);
        clearTimeout(clearTimer);
      };
    }
  }, [targetContactName, targetContactPulse, knownCharacters]);

  // Filter known characters
  const filteredContacts = knownCharacters.filter(c => {
    const q = searchQuery.toLowerCase();
    const name = (c.name || '').toLowerCase();
    const role = (c.basic_info?.role || c.basic_info?.occupation || c.role || '').toLowerCase();
    const faction = (c.basic_info?.faction || c.faction || '').toLowerCase();
    const grade = (c.basic_info?.grade || c.grade || '').toLowerCase();
    const club = (c.basic_info?.club || c.club || '').toLowerCase();
    const anomTag = (c.anomalous_tag_label || c.anomalous_npc_tag || c.basic_info?.anomalous_npc_tag || '').toLowerCase();
    return name.includes(q) || role.includes(q) || faction.includes(q) || grade.includes(q) || club.includes(q) || anomTag.includes(q);
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
    const npc = (c.target_display_name || c.npc_name || c.target_npc || c.target_entity || '').toLowerCase();
    return text.includes(q) || npc.includes(q);
  });

  const findDiscoveredContact = (itemOrName) => {
    if (!itemOrName) return null;
    const rawName = typeof itemOrName === 'string'
      ? itemOrName.split('(')[0].trim()
      : String(itemOrName.name || itemOrName.title || '').split('(')[0].trim();
    const rawNpcId = typeof itemOrName === 'object' ? String(itemOrName.npc_id ?? '').trim().toLowerCase() : '';
    const normName = rawName.toLowerCase();
    if (!normName && !rawNpcId) return null;
    return knownCharacters.find(c => {
      const cName = String(c.name ?? '').trim().toLowerCase();
      const cNpcId = String(c.npc_id ?? '').trim().toLowerCase();
      return (normName && cName === normName) || (rawNpcId && (cNpcId === rawNpcId || cName.replace(/\s+/g, '_') === rawNpcId));
    }) || null;
  };

  const jumpToContact = (matched) => {
    if (!matched) return;
    if (matched.is_contact && onJumpToSavedContact) {
      onJumpToSavedContact(matched.name);
      return;
    }
    setSubTab('contacts');
    setSearchQuery('');
    setExpandedNpc(matched.id || matched.name);
  };

  const renderLinkedPerson = (item, textClassName = '') => {
    if (!item) return null;
    if (typeof item === 'object' && item.locked) {
      return <span className="text-gray-500 italic">{item.message}</span>;
    }
    const label = formatPersonEntity(item);
    const matched = findDiscoveredContact(item);
    if (!matched) {
      return <span className={textClassName}>{label}</span>;
    }
    const rawName = typeof item === 'string' ? label : (item.name || item.title || label);
    const roleSuffix = typeof item === 'object'
      ? (item.role || item.closeness || item.type || item.grade || item.relationship_type || '')
      : '';
    return (
      <span className={textClassName}>
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); jumpToContact(matched); }}
          className="underline decoration-dotted underline-offset-2 hover:text-fantasy-accent transition-colors cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded-xs"
        >
          {rawName}
        </button>
        {roleSuffix ? ` (${roleSuffix})` : ''}
      </span>
    );
  };

  const handleCancelAgendaItem = async (commitmentId, titleLabel) => {
    if (!commitmentId || !cancelCommitment || cancellingCommitmentId) return;
    setCancellingCommitmentId(commitmentId);
    setCompanionFeedback(null);
    try {
      await cancelCommitment(commitmentId, 'player_cancelled');
      setCompanionFeedback({
        type: 'ok',
        text: t('codex.cancelled_commitment', { title: titleLabel, defaultValue: `Cancelled "${titleLabel}".` }),
      });
    } catch (err) {
      setCompanionFeedback({ type: 'error', text: err.message || 'Could not cancel commitment.' });
    } finally {
      setCancellingCommitmentId(null);
    }
  };

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
            aria-label={
              subTab === 'contacts'
                ? t('codex.search_known_characters', 'Search Known Characters...')
                : t('codex.search_placeholder', { category: t(`codex.${subTab}`, subTab), defaultValue: `Search ${subTab}...` })
            }
            placeholder={
              subTab === 'contacts'
                ? t('codex.search_known_characters', 'Search Known Characters...')
                : t('codex.search_placeholder', { category: t(`codex.${subTab}`, subTab), defaultValue: `Search ${subTab}...` })
            }
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
              filteredContacts.map(rawNpc => {
                const npcToggleKey = rawNpc.id || rawNpc.name;
                const isDebugRevealed = Boolean(rawNpc.debug_revealed);
                const npc = (isDebugRevealed && rawNpc.debug_profile)
                  ? {
                      ...rawNpc,
                      ...rawNpc.debug_profile,
                      appearance: { ...(rawNpc.appearance || {}), ...(rawNpc.debug_profile.appearance || {}) },
                      basic_info: { ...(rawNpc.basic_info || {}), ...(rawNpc.debug_profile.basic_info || {}) },
                    }
                  : rawNpc;
                const score = npc.relationship_score || npc.affinity || 0;
                const isRomantic = (npc.track === 'romantic') || (npc.relations?.track === 'romantic');
                const tier = getRelationshipTier(score, isRomantic ? 'romantic' : 'platonic', t);
                const isExpanded = expandedNpc === npcToggleKey;
                const isInParty = partyNpcNames.has((npc.name || '').toLowerCase());
                const basic = npc.basic_info || {};
                const anomTag = npc.anomalous_npc_tag || basic.anomalous_npc_tag || null;
                const isSpecialAgent = anomTag === 'special_agent';
                const isCivilianTag = anomTag === 'civilian';
                const isDeceased = Boolean(
                  npc.deceased ||
                  basic.deceased ||
                  String(npc.disposition || '').toLowerCase() === 'dead'
                );
                const isMerchant = /merchant|shopkeeper|vendor|apothecary|peddler|trader/i.test(basic.role || basic.occupation || npc.name || '');
                const isNonCombatScen = ['high_school_drama', 'high_school', 'slice_of_life', 'cozy_cafe'].includes((session?.scenario || '').toLowerCase());
                const isDetailedUnlocked = score >= 100 || isInParty || isDebugRevealed;
                const isCombatDossierUnlocked = isDetailedUnlocked || Boolean(npc.same_faction_colleague);
                const canRecruit = !isNonCombatScen && !isMerchant && !isCivilianTag && !isDeceased;
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

                const isSavedContact = Boolean(npc.is_contact);
                const hasOperationalDetails = Boolean(isInParty || isSpecialAgent || isCivilianTag || isDebugRevealed);

                return (
                  <div 
                    key={npc.id || npc.name}
                    ref={(el) => {
                      cardRefs.current[npcToggleKey] = el;
                      if (npc.name) cardRefs.current[String(npc.name).toLowerCase()] = el;
                    }}
                    className={`bg-black/50 border rounded-lg p-2.5 space-y-1.5 transition-all ${
                      highlightedNpcKey === npcToggleKey
                        ? 'border-fantasy-accent ring-2 ring-fantasy-accent/60 shadow-lg shadow-fantasy-accent/20'
                        : 'border-fantasy-border/60 hover:border-fantasy-border'
                    }`}
                  >
                    {/* Surface Encounter Directory Header */}
                    <div className="flex items-start justify-between gap-2 select-none">
                      <div className="flex items-center gap-2 min-w-0">
                        <div className={`w-8 h-8 rounded-full flex items-center justify-center border font-bold text-xs shrink-0 ${
                          isRomantic 
                            ? 'bg-pink-950/40 border-pink-700/60 text-pink-300' 
                            : 'bg-fantasy-dark border-fantasy-accent/40 text-fantasy-accent'
                        }`}>
                          {isRomantic ? <Heart size={14} /> : <User size={14} />}
                        </div>
                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className={`font-bold text-xs sm:text-sm ${isDeceased ? 'line-through text-gray-400' : 'text-gray-100'}`}>{npc.name}</span>
                            {isSavedContact && (
                              <button
                                type="button"
                                onClick={(e) => {
                                  e.stopPropagation();
                                  if (onJumpToSavedContact) onJumpToSavedContact(npc.name);
                                }}
                                title={t('codex.open_in_contacts', 'Open Full Dossier in Contacts')}
                                className="text-[9px] px-1.5 py-0.5 bg-emerald-950/75 hover:bg-emerald-900/80 text-emerald-300 rounded font-bold uppercase border border-emerald-700/60 inline-flex items-center gap-1 cursor-pointer transition-colors"
                              >
                                <Smartphone size={9} />
                                <span>{t('codex.saved_contact', 'Saved Contact')}</span>
                              </button>
                            )}
                            {isSpecialAgent && (
                              <span className="text-[9px] px-1.5 py-0.2 bg-cyan-950/70 text-cyan-300 rounded font-bold uppercase border border-cyan-700/50">
                                ⚡ {t('codex.special_agent', 'Special Agent')}
                              </span>
                            )}
                            {isCivilianTag && (
                              <span className="text-[9px] px-1.5 py-0.2 bg-slate-900/80 text-slate-300 rounded font-semibold uppercase border border-slate-700/60">
                                {t('codex.civilian', 'Civilian')}
                              </span>
                            )}
                            {isDeceased && (
                              <span className="text-[9px] px-1.5 py-0.2 bg-rose-950/80 text-rose-300 rounded font-bold uppercase border border-rose-700/60">
                                💀 {t('codex.deceased', 'Deceased')}
                              </span>
                            )}
                            {isInParty && (
                              <span className="text-[9px] px-1.5 py-0.2 bg-purple-950/60 text-purple-300 rounded font-bold uppercase border border-purple-800/40">
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
                            {npc.public_role || basic.public_role || basic.role || basic.occupation || (basic.faction ? `${basic.faction} Member` : 'Encountered')}
                          </span>
                        </div>
                      </div>

                      <div className="flex items-center gap-1.5 text-right shrink-0">
                        <div>
                          <span className={`text-[11px] font-bold block ${tier.color}`}>
                            {tier.label}
                          </span>
                          <span className="font-mono text-[10px] font-semibold text-gray-300">
                            {score > 0 ? `+${score}` : score}
                          </span>
                        </div>
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
                        {(npc.public_role || basic.public_role || basic.role || basic.occupation || npc.role) && (
                          <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border/50 text-[10.5px]">
                            Role: <strong className="text-gray-100">{npc.public_role || basic.public_role || basic.role || basic.occupation || npc.role}</strong>
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
                            <span>{formatCleanLocation(basic.location || npc.location)}</span>
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
                            {isNsfwScenario && (isMale ? ((infoLevel >= 3 || isDebugRevealed) && appearance.penis_size && appearance.penis_size.toLowerCase() !== 'unknown') : appearance.breast_size) && (
                              <span className="text-pink-400/90 font-medium">
                                🔞 {isMale ? `Size: ${appearance.penis_size}` : `Bust: ${appearance.breast_size}`}
                              </span>
                            )}
                          </div>
                        );
                      })()}

                      {/* Surface Directory Footer: Open Saved Contact Dossier or Operational Details */}
                      <div className="flex items-center justify-between pt-1 border-t border-fantasy-border/30 gap-2 flex-wrap">
                        {isSavedContact && onJumpToSavedContact ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              onJumpToSavedContact(npc.name);
                            }}
                            className="flex items-center gap-1.5 py-1 px-2.5 rounded text-[11px] font-bold border bg-emerald-950/50 hover:bg-emerald-900/60 border-emerald-700/60 text-emerald-300 transition-all cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-emerald-400"
                          >
                            <Smartphone size={12} />
                            <span>{t('codex.open_in_contacts', 'Open in Contacts')}</span>
                            <ChevronRight size={12} />
                          </button>
                        ) : isDebugRevealed ? (
                          <button
                            type="button"
                            aria-expanded={isExpanded}
                            onClick={(e) => {
                              e.stopPropagation();
                              setExpandedNpc(isExpanded ? null : npcToggleKey);
                            }}
                            className="flex items-center gap-1.5 py-1 px-2.5 rounded text-[11px] font-bold border bg-purple-950/50 hover:bg-purple-900/60 border-purple-700/60 text-purple-200 transition-all cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-purple-400"
                          >
                            {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                            <span>{t('codex.full_debug_dossier', 'Full Debug Dossier')}</span>
                          </button>
                        ) : (
                          <span className="text-[10px] text-gray-500 italic flex items-center gap-1">
                            <Lock size={10} className="text-amber-400/70 shrink-0" />
                            <span>{t('codex.unlock_contact_hint', 'Unlock as a Contact to view personal dossier')}</span>
                          </span>
                        )}

                        <div className="flex items-center gap-1.5">
                          {isDebugRevealed && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/60 font-mono">
                              {t('codex.debug_revealed_badge', 'DEBUG: Full Profile Revealed')}
                            </span>
                          )}
                          {hasOperationalDetails && (
                            <button
                              type="button"
                              aria-expanded={isExpanded}
                              onClick={(e) => {
                                e.stopPropagation();
                                setExpandedNpc(isExpanded ? null : npcToggleKey);
                              }}
                              className="flex items-center gap-1 py-1 px-2 rounded text-[10.5px] font-semibold border bg-black/50 hover:bg-black/70 border-fantasy-border/60 text-gray-300 transition-all cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent"
                            >
                              {isExpanded ? <ChevronDown size={11} /> : <ChevronRight size={11} />}
                              <span>{isDebugRevealed ? t('codex.full_debug_dossier', 'Full Debug Dossier') : t('codex.operational_info', 'Field Status')}</span>
                            </button>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Expanded Operational / Debug Details (Personal Dossiers live in Contacts tab) */}
                    {isExpanded && hasOperationalDetails && (
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

                        {/* Anomalous Incursions: Operative Combat Dossier & Civilian Classification */}
                        {isSpecialAgent && (() => {
                          const agentTier = npc.agent_tier || basic.agent_tier || 1;
                          const rankTitle = npc.rank_title || basic.rank_title || `Tier ${agentTier} Operative`;
                          const agentClass = npc.agent_class || basic.agent_class || basic.role || 'Special Agent';
                          const cMaxHp = npc.combat_max_hp ?? 130;
                          const cHp = npc.combat_hp ?? cMaxHp;
                          const cMaxMp = npc.combat_max_mp ?? 60;
                          const cMp = npc.combat_mp ?? cMaxMp;
                          const wName = npc.weapon_profile?.name || '';
                          const abilities = (
                            isDebugRevealed
                              ? (npc.debug_innate_ability_details || npc.innate_ability_details)
                              : npc.innate_ability_details
                          ) || [];

                          return (
                            <div className="bg-cyan-950/20 border border-cyan-800/50 rounded-lg p-2.5 space-y-2">
                              <div className="flex items-center justify-between gap-2 flex-wrap">
                                <span className="text-[11px] font-bold text-cyan-300 uppercase tracking-wider flex items-center gap-1">
                                  <span>⚡</span>
                                  <span>{t('codex.operative_dossier', 'Operative Combat Dossier')}</span>
                                </span>
                                <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-cyan-950/70 text-cyan-200 border border-cyan-700/50 font-semibold">
                                  Tier {agentTier} • {rankTitle}
                                </span>
                              </div>

                              <div className="flex flex-wrap items-center gap-1.5 text-[10.5px]">
                                <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border/50">
                                  Class: <strong className="text-white">{agentClass}</strong>
                                </span>
                                <span className="px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40 font-mono">
                                  ❤️ {cHp}/{cMaxHp} HP
                                </span>
                                <span className="px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300 border border-blue-800/40 font-mono">
                                  💧 {cMp}/{cMaxMp} MP
                                </span>
                                {wName && (
                                  <span className="px-1.5 py-0.5 rounded bg-amber-950/35 text-amber-200 border border-amber-800/40">
                                    ⚔️ {wName}
                                  </span>
                                )}
                              </div>

                              {isCombatDossierUnlocked && abilities.length > 0 ? (
                                <div className="space-y-1 pt-1 border-t border-cyan-900/40">
                                  <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400 block">
                                    {t('codex.innate_abilities', 'Innate Special Abilities')}
                                  </span>
                                  <div className="grid grid-cols-1 gap-1">
                                    {abilities.map((ab, abIdx) => (
                                      <div
                                        key={ab.id || abIdx}
                                        className={`p-1.5 rounded border text-[10.5px] leading-snug ${
                                          ab.is_ultimate
                                            ? 'bg-purple-950/35 border-purple-700/50 text-purple-100'
                                            : 'bg-black/50 border-fantasy-border/40 text-gray-300'
                                        }`}
                                      >
                                        <div className="flex items-center justify-between gap-1.5">
                                          <span className="font-semibold text-gray-100 flex items-center gap-1">
                                            <span>{ab.emoji || '✨'}</span>
                                            <span>{ab.name}</span>
                                            {ab.is_ultimate && (
                                              <span className="text-[8.5px] px-1 py-0.2 rounded bg-purple-900/80 text-purple-200 border border-purple-600/50 font-mono uppercase">
                                                Ultimate
                                              </span>
                                            )}
                                          </span>
                                          <span className="text-[9.5px] font-mono text-cyan-300 shrink-0">
                                            {ab.mp_cost ?? 10} MP
                                          </span>
                                        </div>
                                        {ab.desc && (
                                          <p className="text-[10px] text-gray-400 mt-0.5">{ab.desc}</p>
                                        )}
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              ) : (
                                <p className="text-[10px] text-gray-400 italic pt-1 border-t border-cyan-900/40">
                                  🔒 {t('codex.abilities_locked_note', 'Reach Friend standing (100+ Affinity) or recruit into your party to reveal innate abilities.')}
                                </p>
                              )}
                            </div>
                          );
                        })()}

                        {isCivilianTag && (
                          <div className={`p-2.5 rounded-lg border space-y-1 ${
                            isDeceased
                              ? 'bg-rose-950/25 border-rose-800/50 text-rose-200'
                              : 'bg-slate-950/60 border-slate-700/60 text-slate-300'
                          }`}>
                            <div className="flex items-center justify-between gap-2 flex-wrap">
                              <span className="text-[11px] font-bold uppercase tracking-wider flex items-center gap-1">
                                <span>{isDeceased ? '💀' : '👤'}</span>
                                <span>{t('codex.civilian_classification', 'Civilian Classification')}</span>
                              </span>
                              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/50 text-gray-300 border border-slate-700/50">
                                100 HP • 0 MP (Unawakened)
                              </span>
                            </div>
                            <p className="text-[10.5px] text-gray-400 leading-snug">
                              {isDeceased
                                ? t('codex.civilian_deceased_note', 'Perished permanently during an anomalous incursion due to lacking innate mana protection.')
                                : t('codex.civilian_party_note', 'Mundane citizen with no mana or special abilities. Eligible as a Contact, but cannot be recruited into your field party.')}
                            </p>
                          </div>
                        )}

                        {isDebugRevealed && (
                          <div className="space-y-2.5 pt-1">
                            {/* 4-Tab Debug Dossier Header */}
                            <div
                              role="tablist"
                              aria-label={`${npc.name} debug dossier sections`}
                              className="grid grid-cols-4 border-b border-purple-700/60 pt-1.5 px-1 bg-purple-950/30 rounded-t-lg gap-1 items-end select-none"
                            >
                              {DEBUG_DOSSIER_TABS.map(tb => {
                                const isActive = debugDossierTab === tb.id;
                                return (
                                  <button
                                    key={tb.id}
                                    type="button"
                                    role="tab"
                                    aria-selected={isActive}
                                    title={tb.fullLabel}
                                    onClick={(e) => { e.stopPropagation(); setDebugDossierTab(tb.id); }}
                                    className={`min-w-0 py-1.5 px-1 text-xs font-bold transition-all flex items-center justify-center gap-1 rounded-t-md relative cursor-pointer ${
                                      isActive
                                        ? 'bg-black/60 text-purple-200 border-t-2 border-t-purple-400 border-x border-purple-700/60 border-b-black/60 -mb-px z-10'
                                        : 'bg-black/25 text-gray-400 hover:text-gray-200 hover:bg-black/40 border-t border-x border-transparent border-b border-b-purple-700/60'
                                    }`}
                                  >
                                    <span className="text-xs shrink-0">{tb.icon}</span>
                                    <span className="truncate text-[10.5px] font-semibold">{tb.shortLabel}</span>
                                  </button>
                                );
                              })}
                            </div>

                            {/* 4-Tab Debug Dossier Body */}
                            <div role="tabpanel" className="bg-black/50 border-x border-b border-purple-700/60 rounded-b-lg p-3 text-xs -mt-2.5 space-y-3">
                              {debugDossierTab === 'persona' && (
                                <div className="space-y-2.5">
                                  {(npc.archetype_trope || basic.archetype_trope) && (
                                    <div className="text-[11px] text-purple-300">
                                      <strong className="text-purple-200">Archetype / Trope:</strong> {npc.archetype_trope || basic.archetype_trope}
                                    </div>
                                  )}
                                  {(basic.description || appearance.summary || npc.description) && (
                                    <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 text-gray-300 leading-relaxed">
                                      <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">
                                        📖 Background & Notes
                                      </span>
                                      {basic.description || appearance.summary || npc.description}
                                    </div>
                                  )}
                                  {(basic.mannerisms || appearance.mannerisms || npc.mannerisms) && (
                                    <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 text-gray-300 leading-relaxed">
                                      <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-0.5">
                                        🎭 Mannerisms
                                      </span>
                                      {basic.mannerisms || appearance.mannerisms || npc.mannerisms}
                                    </div>
                                  )}
                                  {traits.length > 0 && (
                                    <div>
                                      <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                        Known Traits
                                      </span>
                                      <div className="flex flex-wrap gap-1">
                                        {traits.map((tr, idx) => (
                                          <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-black/60 text-gray-200 border border-fantasy-border">
                                            {typeof tr === 'string' ? tr : (tr.trait || tr.name)}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  {preferences.length > 0 && (
                                    <div>
                                      <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                        Likes & Preferences
                                      </span>
                                      <div className="flex flex-wrap gap-1">
                                        {preferences.map((p, idx) => (
                                          <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40">
                                            {p}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                  {dislikes.length > 0 && (
                                    <div>
                                      <span className="text-[10.5px] font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                        Dislikes & Pet Peeves
                                      </span>
                                      <div className="flex flex-wrap gap-1">
                                        {dislikes.map((d, idx) => (
                                          <span key={idx} className="text-[11px] px-2 py-0.5 rounded bg-red-950/40 text-red-300 border border-red-800/40">
                                            {d}
                                          </span>
                                        ))}
                                      </div>
                                    </div>
                                  )}
                                </div>
                              )}

                              {debugDossierTab === 'history' && (() => {
                                const recentMemories = Array.isArray(npc.recent_memories)
                                  ? npc.recent_memories
                                  : (Array.isArray(npc.rel_history) ? npc.rel_history : []);
                                return (
                                  <div className="space-y-2.5">
                                    {(basic.primary_facility || basic.secondary_facility || basic.location || npc.location) && (
                                      <div className="bg-black/40 p-2 rounded border border-fantasy-border/40 space-y-1 text-[11px]">
                                        <span className="font-bold text-amber-400 uppercase tracking-wider block">
                                          📍 Schedule & Haunts
                                        </span>
                                        {basic.primary_facility && <div>• <strong>Primary Facility:</strong> {basic.primary_facility}</div>}
                                        {basic.secondary_facility && <div>• <strong>Secondary Hangout:</strong> {basic.secondary_facility}</div>}
                                        {(basic.location || npc.location) && <div>• <strong>Current / Last Seen:</strong> {formatCleanLocation(basic.location || npc.location)}</div>}
                                      </div>
                                    )}
                                    <div className="space-y-1.5">
                                      <span className="text-[10.5px] font-bold text-amber-400 uppercase tracking-wider block">
                                        📜 Shared Interactions ({recentMemories.length})
                                      </span>
                                      {recentMemories.length === 0 ? (
                                        <p className="text-gray-500 italic text-[11px]">No shared interactions recorded yet.</p>
                                      ) : (
                                        recentMemories.map((mem, idx) => {
                                          const text = typeof mem === 'string' ? mem : (mem.memory_fact || mem.summary || JSON.stringify(mem));
                                          return (
                                            <div key={idx} className="p-2 rounded bg-black/50 border border-fantasy-border/30 text-gray-200 text-[11px]">
                                              • {text}
                                            </div>
                                          );
                                        })
                                      )}
                                    </div>
                                  </div>
                                );
                              })()}

                              {debugDossierTab === 'relations' && (() => {
                                const disRel = npc.disclosed_relations || {};
                                const romData = disRel.romance || relations.romance || {};
                                const famData = disRel.family || {};
                                const friendsList = disRel.friends?.members || relations.friends || [];
                                const rivalsList = disRel.rivals?.members || relations.rivals || [];
                                return (
                                  <div className="space-y-2.5 text-[11px]">
                                    <div>
                                      <span className="font-bold text-fantasy-accent uppercase tracking-wider block mb-1">
                                        👨‍👩‍👧‍👦 Immediate Family Tree
                                      </span>
                                      {famData.members && famData.members.length > 0 ? (
                                        <div className="space-y-1">
                                          {famData.members.map((mem, i) => (
                                            <div key={i} className="text-gray-300">
                                              • <strong>{mem.relation || 'Relative'}:</strong> {renderLinkedPerson(mem)} {mem.race ? `(${formatRace(mem.race)})` : ''}
                                            </div>
                                          ))}
                                        </div>
                                      ) : Array.isArray(familyTree) && familyTree.length > 0 ? (
                                        <div className="space-y-1">
                                          {familyTree.map((mem, i) => (
                                            <div key={i} className="text-gray-300">
                                              • <strong>{mem.relation || 'Relative'}:</strong> {renderLinkedPerson(mem.name || mem)}
                                            </div>
                                          ))}
                                        </div>
                                      ) : (
                                        <p className="text-gray-500 italic">No family records recorded.</p>
                                      )}
                                    </div>
                                    <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                                      <span className="font-bold text-pink-400 uppercase tracking-wider block">
                                        💖 Romantic Standing
                                      </span>
                                      <div>
                                        • <strong>Current Status:</strong>{' '}
                                        {romData.current_partner
                                          ? renderLinkedPerson(romData.current_partner, 'text-pink-300 font-semibold')
                                          : (romData.status || 'Single')}
                                      </div>
                                      {romData.ex_partners && romData.ex_partners.length > 0 && (
                                        <div>
                                          • <strong>Past Ex-Partner(s):</strong>{' '}
                                          {romData.ex_partners.map((p, idx) => (
                                            <React.Fragment key={idx}>
                                              {idx > 0 ? ', ' : ''}
                                              {renderLinkedPerson(p)}
                                            </React.Fragment>
                                          ))}
                                        </div>
                                      )}
                                    </div>
                                    <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                                      <span className="font-bold text-cyan-400 uppercase tracking-wider block">🤝 Friends</span>
                                      {friendsList.length > 0 ? (
                                        friendsList.map((f, i) => <div key={i} className="text-cyan-300">• {renderLinkedPerson(f)}</div>)
                                      ) : (
                                        <p className="text-gray-500 italic">No close friends recorded.</p>
                                      )}
                                    </div>
                                    <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                                      <span className="font-bold text-amber-400 uppercase tracking-wider block">⚔️ Rivals</span>
                                      {rivalsList.length > 0 ? (
                                        rivalsList.map((r, i) => <div key={i} className="text-amber-300">• {renderLinkedPerson(r)}</div>)
                                      ) : (
                                        <p className="text-gray-500 italic">No known rivals recorded.</p>
                                      )}
                                    </div>
                                  </div>
                                );
                              })()}

                              {debugDossierTab === 'intimate' && (() => {
                                const intSec = npc.intimate_sections || {};
                                const hasSections = Boolean(intSec.anatomy && intSec.dynamic);
                                const bSize = appearance.breast_size || 'Modest B-Cup';
                                const pSize = appearance.penis_size || 'Average';
                                const sizeDisplay = isMale ? formatTitle(pSize) : formatTitle(bSize);
                                return (
                                  <div className="space-y-2.5 text-[11px]">
                                    <div>
                                      <span className="font-bold text-pink-400 uppercase tracking-wider block mb-1">
                                        🔞 Anatomy & Experience
                                      </span>
                                      {hasSections && intSec.anatomy ? (
                                        renderBulletPoints(intSec.anatomy)
                                      ) : (
                                        <div className="space-y-1 text-gray-300">
                                          <div>• <strong>{isMale ? 'Penis Size' : 'Breast Size'}:</strong> {sizeDisplay}</div>
                                          <div>• <strong>Intercourse:</strong> {appearance.experience || (appearance.intercourse_experience === 'virgin' ? 'Virgin' : 'Non-Virgin')}</div>
                                          <div>• <strong>Oral:</strong> {appearance.oral_experience || 'Inexperienced'}</div>
                                          <div>• <strong>Manual:</strong> {appearance.manual_experience || 'Inexperienced'}</div>
                                          <div>• <strong>Anal:</strong> {appearance.anal_experience || 'Inexperienced'}</div>
                                        </div>
                                      )}
                                    </div>
                                    {hasSections && intSec.dynamic && (
                                      <div className="pt-2 border-t border-fantasy-border/30">
                                        <span className="font-bold text-purple-400 uppercase tracking-wider block mb-1">🎭 Demeanor & Dynamic</span>
                                        {renderBulletPoints(intSec.dynamic)}
                                      </div>
                                    )}
                                    {hasSections && intSec.undergarments && (
                                      <div className="pt-2 border-t border-fantasy-border/30">
                                        <span className="font-bold text-indigo-400 uppercase tracking-wider block mb-1">🩲 Undergarments</span>
                                        {renderBulletPoints(intSec.undergarments)}
                                      </div>
                                    )}
                                    {hasSections && (intSec.sensitive_spots || intSec.sensitivities) && (
                                      <div className="pt-2 border-t border-fantasy-border/30">
                                        <span className="font-bold text-pink-400 uppercase tracking-wider block mb-1">🌸 Sensitive Spots & Desires</span>
                                        {renderBulletPoints(intSec.sensitive_spots || intSec.sensitivities)}
                                      </div>
                                    )}
                                    {hasSections && intSec.desires_and_turn_offs && (
                                      <div className="pt-2 border-t border-fantasy-border/30">
                                        <span className="font-bold text-amber-400 uppercase tracking-wider block mb-1">🔥 Desires & Turn-Offs</span>
                                        {renderBulletPoints(intSec.desires_and_turn_offs)}
                                      </div>
                                    )}
                                    {hasSections && intSec.act_preferences && (
                                      <div className="pt-2 border-t border-fantasy-border/30">
                                        <span className="font-bold text-rose-400 uppercase tracking-wider block mb-1">❤️ Act Preferences</span>
                                        {renderBulletPoints(intSec.act_preferences)}
                                      </div>
                                    )}
                                    <div className="pt-2 border-t border-fantasy-border/30">
                                      <span className="font-bold text-gray-300 uppercase tracking-wider block mb-1">Past Intimate History</span>
                                      {npc.past_intimate_entries && npc.past_intimate_entries.length > 0 ? (
                                        npc.past_intimate_entries.map((h, i) => <p key={i} className="text-gray-300 italic">• {h}</p>)
                                      ) : npc.past_intimate_history ? (
                                        <p className="text-gray-300 italic">• {npc.past_intimate_history}</p>
                                      ) : (
                                        <p className="text-gray-400 italic">• Virgin (No prior intimate history before meeting you)</p>
                                      )}
                                    </div>
                                  </div>
                                );
                              })()}
                            </div>
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
                            <span>HQ: {formatCleanLocation(faction.hq_location_id)}</span>
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
                      <p className="text-[11px] text-gray-400 leading-snug">{cleanProseLocations(ent.description)}</p>
                    )}

                    {ent.location && (
                      <span className="text-[10px] text-gray-500 flex items-center gap-1">
                        <MapPin size={10} />
                        <span>{formatCleanLocation(ent.location)}</span>
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
                  const cId = c.commitment_id || c.id;
                  const cType = (c.commitment_type || 'promise').toLowerCase();
                  const isRendezvous = cType === 'rendezvous';
                  const isArrived = c.status === 'arrived';
                  const isFulfilled = c.status === 'fulfilled';
                  const isFlaked = c.status === 'flaked' || c.status === 'broken';
                  const isConfidential = Boolean(c.is_confidential);
                  const shortLoc = formatCleanLocation(c.target_location || c.rendezvous_location || '', { includeZone: false });
                  const targetName = c.target_display_name || c.npc_name || c.target_entity || 'Counterparty';
                  const subtypeLabel = (c.subtype || cType).replace(/_/g, ' ');
                  const canCancel = Boolean(cId && ['active', 'pending', 'arrived'].includes((c.status || 'active').toLowerCase()));
                  const cardTitle = c.title || (isRendezvous ? `Meetup with ${targetName}` : `Promise to ${targetName}`);
                  const matchedTarget = findDiscoveredContact({ name: targetName, npc_id: c.npc_id || c.target_entity });

                  const fmtMin = (m) => {
                    const clean = Math.max(0, Number(m || 0)) % 1440;
                    return `${String(Math.floor(clean / 60)).padStart(2, '0')}:${String(clean % 60).padStart(2, '0')}`;
                  };
                  const timeWindowLabel = c.time_window_label || (
                    isRendezvous && c.scheduled_day
                      ? `Day ${c.scheduled_day} • ${fmtMin(c.start_minute)}–${fmtMin(c.end_minute)}`
                      : (c.scheduled_day ? `Day ${c.scheduled_day}` : 'Open Obligation')
                  );

                  const hasOverlapConflict = isRendezvous && filteredCommitments.some(other => {
                    if (!other || (other.commitment_id || other.id) === cId || (other.commitment_key && other.commitment_key === c.commitment_key) || other.commitment_type !== 'rendezvous') return false;
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
                      key={cId || c.commitment_key || idx}
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
                            {cardTitle}
                          </h5>
                          <span className="text-[9px] px-1.5 py-0.2 rounded bg-fantasy-dark text-gray-300 border border-fantasy-border/60 uppercase font-mono">
                            {subtypeLabel}
                          </span>
                          {hasOverlapConflict && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                              ⚠️ Overlap
                            </span>
                          )}
                        </div>

                        <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono uppercase font-bold border shrink-0 ${
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
                        {cleanProseLocations(c.description || c.topic || 'No details provided.')}
                      </p>

                      <div className="flex flex-wrap items-center justify-between text-[10px] text-gray-400 pt-2 mt-2 border-t border-fantasy-border/30 gap-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <span>
                            👤{' '}
                            {matchedTarget ? (
                              <button
                                type="button"
                                onClick={() => jumpToContact(matchedTarget)}
                                className="underline decoration-dotted underline-offset-2 hover:text-fantasy-accent font-semibold text-gray-200 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded-xs"
                              >
                                {targetName}
                              </button>
                            ) : (
                              <strong className="text-gray-200">{targetName}</strong>
                            )}
                          </span>
                          <span className="flex items-center gap-1 font-mono text-gray-400">
                            <Clock size={10} className="text-fantasy-accent shrink-0" />
                            <span>{timeWindowLabel}</span>
                          </span>
                          {isConfidential && (
                            <span className="text-[9px] px-1 py-0.2 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
                              Confidential
                            </span>
                          )}
                        </div>

                        <div className="flex items-center gap-2">
                          {shortLoc && (
                            <span className="flex items-center gap-1 text-gray-400">
                              <MapPin size={10} className="text-fantasy-accent" />
                              <span>{shortLoc}</span>
                            </span>
                          )}
                          {canCancel && (
                            <button
                              type="button"
                              disabled={cancellingCommitmentId === cId}
                              onClick={() => handleCancelAgendaItem(cId, cardTitle)}
                              className="px-2 py-0.5 rounded bg-rose-950/50 hover:bg-rose-900/60 text-rose-300 border border-rose-800/60 text-[10px] font-semibold transition-colors cursor-pointer disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-400"
                            >
                              {cancellingCommitmentId === cId ? '...' : t('codex.cancel_commitment', 'Cancel')}
                              <span className="sr-only"> {cardTitle}</span>
                            </button>
                          )}
                        </div>
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
