import React, { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Smartphone, Users, Heart, Search, MessageCircle, MapPin,
  ChevronDown, ChevronRight, User, UserMinus, Sparkles, Scroll, ShieldAlert
} from 'lucide-react';
import { StatusEffectBadge } from './CharacterSheet';
import { getRelationshipTier } from './CodexPanel';
import { formatCleanLocation } from '../../utils/locationFormat';

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
    if (category === 'half_beast' || category === 'halfbeast') return `${specTitle} Half-Beast`;
    if (category === 'hybrid') return `${specTitle} Hybrid`;
    if (category === 'beastfolk') return `${specTitle} Beastfolk`;
    if (category === 'alien') return `${specTitle} Alien`;
    if (category === 'mutant') return `${specTitle} Mutant`;
    return `${specTitle} ${catTitle}`;
  }
  return formatTitle(clean);
};

const renderBulletPoints = (lines) => {
  if (!lines || !lines.length) return null;
  return (
    <div className="space-y-1">
      {lines.map((line, idx) => {
        let clean = String(line).replace(/^[•\-*]\s*/, '').trim();
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

const DOSSIER_TABS = [
  { id: 'persona', icon: '👤', shortLabel: 'Persona', fullLabel: 'Persona' },
  { id: 'history', icon: '📜', shortLabel: 'History', fullLabel: 'Shared History' },
  { id: 'relations', icon: '🌳', shortLabel: 'Relations', fullLabel: 'Relations & Family' },
  { id: 'intimate', icon: '🔥', shortLabel: 'Intimacy', fullLabel: 'Intimate Dossier' },
];

const ContactsPanel = ({
  codexHook,
  session,
  user,
  onSessionUpdated,
  onMessageContact,
  onJumpToCharacterInCodex,
  targetContactName,
}) => {
  const { t } = useTranslation();
  const { contacts = [], lorebook = {}, loading } = codexHook || {};
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNpc, setExpandedNpc] = useState(null);
  const [contactTab, setContactTab] = useState('persona');
  const [companionBusy, setCompanionBusy] = useState(null);
  const [companionFeedback, setCompanionFeedback] = useState(null);
  const tabRefs = useRef({});

  const personalContacts = useMemo(
    () => (contacts || []).filter(c => !c.is_dispatch_channel),
    [contacts]
  );

  useEffect(() => {
    if (targetContactName) {
      setSearchQuery('');
      const targetLow = String(targetContactName ?? '').toLowerCase();
      const matched = personalContacts.find(c =>
        String(c.name ?? '').toLowerCase() === targetLow ||
        String(c.id ?? '').toLowerCase() === targetLow ||
        String(c.npc_id ?? '').toLowerCase() === targetLow
      );
      if (matched) {
        setExpandedNpc(matched.id || matched.name);
      }
    }
  }, [targetContactName, personalContacts]);

  const partyNpcNames = useMemo(
    () => new Set((session?.party_npcs || []).map(p => (p.name || '').toLowerCase())),
    [session?.party_npcs]
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

  const filteredContacts = useMemo(() => {
    const q = searchQuery.toLowerCase().trim();
    if (!q) return personalContacts;
    return personalContacts.filter(c => {
      const name = (c.name || '').toLowerCase();
      const role = (c.basic_info?.role || c.basic_info?.occupation || c.role || '').toLowerCase();
      const faction = (c.basic_info?.faction || c.faction || '').toLowerCase();
      const grade = (c.basic_info?.grade || c.grade || '').toLowerCase();
      const club = (c.basic_info?.club || c.club || '').toLowerCase();
      const anomTag = (c.anomalous_tag_label || c.anomalous_npc_tag || c.basic_info?.anomalous_npc_tag || '').toLowerCase();
      return name.includes(q) || role.includes(q) || faction.includes(q) || grade.includes(q) || club.includes(q) || anomTag.includes(q);
    });
  }, [personalContacts, searchQuery]);

  const allDiscoveredPersons = useMemo(() => {
    const list = [...personalContacts];
    const seen = new Set(list.map(c => String(c.name ?? '').toLowerCase().trim()));
    (lorebook?.entities || []).forEach(e => {
      if (e.entity_type === 'person' && e.is_discovered !== false) {
        const n = String(e.name ?? '').toLowerCase().trim();
        if (n && !seen.has(n)) {
          seen.add(n);
          list.push(e);
        }
      }
    });
    return list;
  }, [personalContacts, lorebook?.entities]);

  const findLinkedPerson = (itemOrName) => {
    if (!itemOrName) return null;
    const rawName = typeof itemOrName === 'string'
      ? itemOrName.split('(')[0].trim()
      : String(itemOrName.name || itemOrName.title || '').split('(')[0].trim();
    const rawNpcId = typeof itemOrName === 'object' ? String(itemOrName.npc_id ?? '').trim().toLowerCase() : '';
    const normName = rawName.toLowerCase();
    if (!normName && !rawNpcId) return null;
    const inContacts = personalContacts.find(c => {
      const cName = String(c.name ?? '').trim().toLowerCase();
      const cNpcId = String(c.npc_id ?? '').trim().toLowerCase();
      return (normName && cName === normName) || (rawNpcId && (cNpcId === rawNpcId || cName.replace(/\s+/g, '_') === rawNpcId));
    });
    if (inContacts) return { entry: inContacts, isSavedContact: true };
    const inWorld = allDiscoveredPersons.find(c => {
      const cName = String(c.name ?? '').trim().toLowerCase();
      const cNpcId = String(c.npc_id ?? '').trim().toLowerCase();
      return (normName && cName === normName) || (rawNpcId && (cNpcId === rawNpcId || cName.replace(/\s+/g, '_') === rawNpcId));
    });
    if (inWorld) return { entry: inWorld, isSavedContact: false };
    return null;
  };

  const handleJumpToPerson = (matchObj) => {
    if (!matchObj?.entry) return;
    if (matchObj.isSavedContact) {
      setSearchQuery('');
      setExpandedNpc(matchObj.entry.id || matchObj.entry.name);
      setContactTab('persona');
    } else if (onJumpToCharacterInCodex) {
      onJumpToCharacterInCodex(matchObj.entry.name);
    }
  };

  const renderLinkedPerson = (item, textClassName = '') => {
    if (!item) return null;
    if (typeof item === 'object' && item.locked) {
      return <span className="text-gray-500 italic">{item.message}</span>;
    }
    const label = formatPersonEntity(item);
    const matchObj = findLinkedPerson(item);
    if (!matchObj) {
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
          onClick={(e) => { e.stopPropagation(); handleJumpToPerson(matchObj); }}
          className="underline decoration-dotted underline-offset-2 hover:text-fantasy-accent transition-colors cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded-xs"
        >
          {rawName}
        </button>
        {roleSuffix ? ` (${roleSuffix})` : ''}
      </span>
    );
  };

  const handleDossierTabKeyDown = (e, npcKey) => {
    const idx = DOSSIER_TABS.findIndex(tb => tb.id === contactTab);
    if (idx === -1) return;
    let nextIdx = -1;
    if (e.key === 'ArrowRight') nextIdx = (idx + 1) % DOSSIER_TABS.length;
    else if (e.key === 'ArrowLeft') nextIdx = (idx - 1 + DOSSIER_TABS.length) % DOSSIER_TABS.length;
    if (nextIdx >= 0) {
      e.preventDefault();
      const nextTab = DOSSIER_TABS[nextIdx];
      setContactTab(nextTab.id);
      const btn = tabRefs.current[`${npcKey}:${nextTab.id}`];
      if (btn) btn.focus();
    }
  };

  return (
    <div className="bg-black/30 rounded-lg border border-fantasy-border p-2.5 sm:p-3 space-y-2.5 min-h-full flex-1 flex flex-col">
      {/* Header & Search */}
      <div className="space-y-2 border-b border-fantasy-border pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Smartphone size={16} className="text-fantasy-accent" />
            <h3 className="font-rpg font-bold text-xs sm:text-sm text-gray-100 uppercase tracking-wider">
              {t('contacts.title', 'Contacts')}
            </h3>
          </div>
          <span className="text-[10px] font-mono text-gray-400">
            {t('contacts.count', { count: filteredContacts.length, defaultValue: `${filteredContacts.length} Saved` })}
          </span>
        </div>

        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-2 text-gray-500" />
          <input
            type="text"
            aria-label={t('contacts.search_placeholder', 'Search Contacts...')}
            placeholder={t('contacts.search_placeholder', 'Search Contacts...')}
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
            type="button"
            onClick={() => setCompanionFeedback(null)}
            className="text-[10px] opacity-70 hover:opacity-100 ml-2"
            aria-label={t('common.close', 'Close')}
          >
            ✕
          </button>
        </div>
      )}

      {/* Content View */}
      {loading && personalContacts.length === 0 ? (
        <p className="text-xs text-gray-500 italic text-center py-8">Loading saved contacts...</p>
      ) : filteredContacts.length === 0 ? (
        <div className="text-center py-8 px-3 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
          <Users size={24} className="mx-auto mb-1.5 opacity-40" />
          <p className="text-xs">{t('contacts.no_contacts', 'No personal contacts unlocked yet.')}</p>
          <p className="text-[10px] text-gray-500 mt-1">
            {t('contacts.unlock_hint', 'Ask for someone\'s number in conversation, add them on PeerPulse, or reach Friend standing (100+).')}
          </p>
        </div>
      ) : (
        <div className="space-y-3 flex-1 flex flex-col">
          {filteredContacts.map(rawNpc => {
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
            const score = npc.relationship_score ?? npc.affinity ?? 0;
            const isBlocked = Boolean(npc.is_blocked_contact || score <= -50);
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
            const isCombatDossierUnlocked = score >= 100 || isInParty || isDebugRevealed || Boolean(npc.same_faction_colleague);
            const traits = npc.unlocked_traits || [];
            const rawDislikes = npc.dislikes || basic.dislikes || [];
            const dislikes = rawDislikes.map(d => typeof d === 'string' ? d : (d.dislike || d.name || '')).filter(Boolean);
            const rawPreferences = npc.preferences || npc.likes || [];
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
                key={npcToggleKey}
                className={`bg-black/50 border rounded-lg p-2.5 space-y-1.5 transition-all ${
                  isBlocked
                    ? 'border-red-900/60 hover:border-red-700/70'
                    : 'border-fantasy-border/60 hover:border-fantasy-border'
                }`}
              >
                {/* Header Toggle Button */}
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={() => setExpandedNpc(isExpanded ? null : npcToggleKey)}
                  className="w-full text-left flex items-start justify-between cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center border font-bold text-xs shrink-0 ${
                      isBlocked
                        ? 'bg-red-950/60 border-red-700/70 text-red-300'
                        : isRomantic
                          ? 'bg-pink-950/40 border-pink-700/60 text-pink-300'
                          : 'bg-fantasy-dark border-fantasy-accent/40 text-fantasy-accent'
                    }`}>
                      {isBlocked ? <ShieldAlert size={14} /> : isRomantic ? <Heart size={14} /> : <User size={14} />}
                    </div>
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`font-bold text-xs sm:text-sm ${isDeceased ? 'line-through text-gray-400' : 'text-gray-100'}`}>
                          {npc.name}
                        </span>
                        {isBlocked && (
                          <span className="text-[9px] px-1.5 py-0.2 bg-red-950/80 text-red-300 rounded font-bold uppercase border border-red-700/60">
                            🚫 {t('contacts.blocked_badge', 'Blocked')}
                          </span>
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
                        {basic.role || basic.occupation || (basic.faction ? `${basic.faction} Member` : 'Contact')}
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
                    {isExpanded ? <ChevronDown size={14} className="text-gray-400" /> : <ChevronRight size={14} className="text-gray-400" />}
                  </div>
                </button>

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

                {/* Summary Badges + Actions */}
                <div className="pt-1.5 space-y-1.5 text-[11px]">
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
                    {(basic.location || npc.location) && (
                      <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/30 text-[10.5px] flex items-center gap-1">
                        <MapPin size={9} className="text-fantasy-accent" />
                        <span>{formatCleanLocation(basic.location || npc.location)}</span>
                      </span>
                    )}
                  </div>

                  {/* Action Row: Expand Full Dossier + Quick Message */}
                  <div className="flex items-center justify-between pt-1 border-t border-fantasy-border/30 gap-2 flex-wrap">
                    <button
                      type="button"
                      aria-expanded={isExpanded}
                      onClick={(e) => {
                        e.stopPropagation();
                        setExpandedNpc(isExpanded ? null : npcToggleKey);
                      }}
                      className="flex items-center gap-1.5 py-1 px-2.5 rounded text-[11px] font-bold border bg-fantasy-accent/10 hover:bg-fantasy-accent/20 border-fantasy-accent/40 text-fantasy-accent transition-all cursor-pointer select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent"
                    >
                      {isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
                      <span>{isExpanded ? t('codex.view_summary', 'Summary View') : t('codex.view_full_profile', 'View Full Profile')}</span>
                      <span className="sr-only"> {npc.name}</span>
                    </button>

                    <div className="flex items-center gap-1.5">
                      {isDebugRevealed && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/80 text-purple-300 border border-purple-700/60 font-mono">
                          {t('codex.debug_revealed_badge', 'DEBUG: Full Profile Revealed')}
                        </span>
                      )}
                      {onMessageContact && (
                        <button
                          type="button"
                          disabled={isBlocked || isDeceased}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (!isBlocked && !isDeceased) onMessageContact(npc);
                          }}
                          title={
                            isDeceased
                              ? t('codex.deceased', 'Deceased')
                              : isBlocked
                                ? t('phone.blocked_notice', 'This contact has blocked your number due to hostility. Reconcile with them in person first.')
                                : `${t('contacts.message_btn', 'Message')} ${npc.name}`
                          }
                          className={`flex items-center gap-1 py-1 px-2.5 rounded text-[11px] font-bold border transition-all select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400 ${
                            isBlocked || isDeceased
                              ? 'opacity-45 cursor-not-allowed bg-neutral-900/60 border-neutral-700/50 text-gray-500'
                              : 'bg-cyan-950/50 hover:bg-cyan-900/60 border-cyan-700/60 text-cyan-200 cursor-pointer'
                          }`}
                        >
                          <MessageCircle size={12} />
                          <span>{isBlocked ? t('contacts.blocked_badge', 'Blocked') : t('contacts.message_btn', 'Message')}</span>
                        </button>
                      )}
                    </div>
                  </div>
                </div>

                {/* Expanded Full Personal Dossier */}
                {isExpanded && (
                  <div className="space-y-3 pt-2.5 border-t border-fantasy-border/40 text-xs text-gray-300">
                    {isBlocked && (
                      <div className="p-2.5 rounded-lg border border-red-800/60 bg-red-950/35 text-red-200 text-[11px] leading-snug">
                        🚫 {t('phone.blocked_notice', 'This contact has blocked your number due to hostility. Reconcile with them in person first.')}
                      </div>
                    )}

                    {isInParty && (
                      <div className="flex items-center justify-between bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40">
                        <span className="text-xs text-gray-300">
                          {t('codex.in_party_desc', 'Currently traveling in your party.')}
                        </span>
                        <button
                          type="button"
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

                    {/* Anomalous Incursions: Operative Combat Dossier */}
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
                                    {ab.desc && <p className="text-[10px] text-gray-400 mt-0.5">{ab.desc}</p>}
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

                    {/* Dossier Folder Tabs */}
                    <div
                      role="tablist"
                      aria-label={`${npc.name} dossier sections`}
                      onKeyDown={(e) => handleDossierTabKeyDown(e, npcToggleKey)}
                      className="grid grid-cols-4 border-b border-fantasy-border/70 pt-1.5 px-1 bg-black/60 rounded-t-lg gap-1 items-end select-none"
                    >
                      {DOSSIER_TABS.map(tb => {
                        const isActive = contactTab === tb.id;
                        return (
                          <button
                            key={tb.id}
                            ref={(el) => { tabRefs.current[`${npcToggleKey}:${tb.id}`] = el; }}
                            type="button"
                            role="tab"
                            aria-selected={isActive}
                            tabIndex={isActive ? 0 : -1}
                            title={tb.fullLabel}
                            onClick={(e) => { e.stopPropagation(); setContactTab(tb.id); }}
                            className={`min-w-0 py-2 px-1 text-xs font-bold transition-all flex items-center justify-center gap-1 rounded-t-md relative cursor-pointer ${
                              isActive
                                ? 'bg-black/40 text-fantasy-accent border-t-2 border-t-fantasy-accent border-x border-fantasy-border/70 border-b-black/40 -mb-px z-10 shadow-sm'
                                : 'bg-black/25 text-gray-400 hover:text-gray-200 hover:bg-black/40 border-t border-x border-transparent border-b border-b-fantasy-border/70'
                            }`}
                          >
                            <span className="text-xs shrink-0">{tb.icon}</span>
                            <span className="truncate text-[11px] font-semibold">
                              <span className="hidden xl:inline">{tb.fullLabel}</span>
                              <span className="xl:hidden">{tb.shortLabel}</span>
                            </span>
                          </button>
                        );
                      })}
                    </div>

                    {/* Folder Panel Content Body */}
                    <div role="tabpanel" className="bg-black/40 border-x border-b border-fantasy-border/70 rounded-b-lg p-3 text-xs -mt-px space-y-3">
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

                        const canShowMaleSize = isMale && (infoLevel >= 3 || isDebugRevealed) && Boolean(appearance.penis_size) && appearance.penis_size.toLowerCase() !== 'unknown';
                        const hasPhysicalAttributes = Boolean(
                          eyeColor || hairDesc || coatOrSkin || buildDesc || featuresDesc || outfitDesc || (isNsfwScenario && (isMale ? canShowMaleSize : (appearance.breast_size || !isMale)))
                        );

                        return (
                          <div className="space-y-2.5">
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

                            {hasPhysicalAttributes && (() => {
                              const hasVitals = Boolean(
                                eyeColor || buildDesc || (isNsfwScenario && (isMale ? canShowMaleSize : (appearance.breast_size || !isMale)))
                              );
                              const hasDetails = Boolean(hairDesc || coatOrSkin || featuresDesc || outfitDesc);

                              return (
                                <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs space-y-2.5">
                                  <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block flex items-center gap-1.5">
                                    ✨ Physical Appearance
                                  </span>

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
                                      {isNsfwScenario && canShowMaleSize && (
                                        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-purple-950/40 border border-purple-800/50 text-purple-300">
                                          <span className="text-purple-400 font-medium">🔞 Penis Size:</span>
                                          <strong className="text-purple-100 font-medium">
                                            {formatTitle(appearance.penis_size)}
                                          </strong>
                                          {appearance.asset_texture && (
                                            <span className="text-purple-200 text-[10px] italic font-normal">({appearance.asset_texture})</span>
                                          )}
                                        </span>
                                      )}
                                    </div>
                                  )}

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

                            {mannerisms && (
                              <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                  🎭 Mannerisms
                                </span>
                                {mannerisms}
                              </div>
                            )}

                            {(basic.description || appearance.summary || npc.description) && (
                              <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                  📖 Background & Notes
                                </span>
                                {basic.description || appearance.summary || npc.description}
                              </div>
                            )}

                            {traits.length > 0 && (
                              <div>
                                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                                  Known Traits
                                </span>
                                <div className="flex flex-wrap gap-1.5">
                                  {traits.map((tr, idx) => (
                                    <span key={idx} className="text-xs px-2 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border">
                                      {typeof tr === 'string' ? tr : (tr.trait || tr.name)}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

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

                      {/* SUBTAB 2: SHARED HISTORY */}
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

                      {/* SUBTAB 3: RELATIONS & FAMILY */}
                      {contactTab === 'relations' && (() => {
                        const disRel = npc.disclosed_relations || {};
                        const romData = disRel.romance || relations.romance || {};
                        const famData = disRel.family || {};
                        const friendsList = disRel.friends?.members || relations.friends || [];
                        const rivalsList = disRel.rivals?.members || relations.rivals || [];

                        return (
                          <div className="space-y-3">
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
                                    const matchedFam = findLinkedPerson(mem);
                                    return (
                                      <div key={i} className="text-gray-300 leading-snug">
                                        • {rEmoji} <strong>{rel}</strong>:{' '}
                                        {matchedFam ? (
                                          <button
                                            type="button"
                                            onClick={(e) => { e.stopPropagation(); handleJumpToPerson(matchedFam); }}
                                            className="underline decoration-dotted underline-offset-2 hover:text-fantasy-accent transition-colors cursor-pointer font-semibold focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded-xs"
                                          >
                                            {mem.name}
                                          </button>
                                        ) : (
                                          <span>{mem.name}</span>
                                        )}{' '}
                                        {mem.race ? `(${formatRace(mem.race)})` : ''} — {statusDot} {(!isParent && (mem.occupation || mem.grade)) ? <span className="italic text-gray-400">— {mem.occupation || mem.grade}</span> : (mem.occupation ? <span className="italic text-gray-400">— {mem.occupation}</span> : '')}
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
                                        • <strong>{renderLinkedPerson(mem.name || mem)}</strong> {mem.relation ? `(${mem.relation})` : ''} {mem.occupation ? `— ${mem.occupation}` : ''}
                                      </div>
                                    ))
                                  ) : (
                                    <>
                                      {familyTree.parents?.map((p, i) => (
                                        <div key={`p-${i}`} className="text-gray-300 leading-snug">
                                          • Parent: <strong>{renderLinkedPerson(typeof p === 'string' ? p : p.name)}</strong> {p.occupation ? `(${p.occupation})` : ''} {p.status ? `[${p.status}]` : ''}
                                        </div>
                                      ))}
                                      {familyTree.siblings?.map((s, i) => (
                                        <div key={`s-${i}`} className="text-gray-300 leading-snug">
                                          • Sibling: <strong>{renderLinkedPerson(typeof s === 'string' ? s : s.name)}</strong> {s.occupation || s.grade ? `(${s.occupation || s.grade})` : ''} {s.status ? `[${s.status}]` : ''}
                                        </div>
                                      ))}
                                    </>
                                  )}
                                </div>
                              ) : (
                                <p className="text-gray-500 italic text-xs">No family records uncovered yet.</p>
                              )}
                            </div>

                            <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                              <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block">
                                💖 Romantic Standing
                              </span>
                              <div className="space-y-1 leading-relaxed">
                                <div>
                                  • <strong className="text-gray-200">Current Status</strong>:{' '}
                                  {romData.current_partner ? (
                                    <span className="text-pink-300 font-semibold">
                                      💖 {renderLinkedPerson(romData.current_partner, 'text-pink-300 font-semibold')}
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
                                        🤫 {renderLinkedPerson(romData.secret_partner, 'text-rose-400 font-semibold')}
                                      </span>
                                    )}
                                  </div>
                                )}

                                <div>
                                  • <strong className="text-gray-200">Past Ex-Partner(s)</strong>:{' '}
                                  {romData.ex_partners && romData.ex_partners.length > 0 ? (
                                    <span className="text-gray-300">
                                      💔{' '}
                                      {romData.ex_partners.map((p, idx) => (
                                        <React.Fragment key={idx}>
                                          {idx > 0 ? ', ' : ''}
                                          {renderLinkedPerson(p)}
                                        </React.Fragment>
                                      ))}
                                    </span>
                                  ) : (romData.revealed || infoLevel >= 2 || isDebugRevealed) ? (
                                    <span className="text-gray-400 italic">None (No prior romantic partners)</span>
                                  ) : (
                                    <span className="text-gray-500 italic">🔒 Locked (Requires Info Level 2+)</span>
                                  )}
                                </div>
                              </div>
                            </div>

                            <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                              <span className="text-xs font-bold text-cyan-400 uppercase tracking-wider block">
                                🤝 Friends
                              </span>
                              {friendsList.length > 0 ? (
                                <div className="space-y-1">
                                  {friendsList.map((f, i) => (
                                    <div key={i} className="text-cyan-300 font-medium">
                                      • 🤝 {renderLinkedPerson(f, 'text-cyan-300 font-medium')}
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-gray-500 italic text-xs">No close friends recorded.</p>
                              )}
                            </div>

                            <div className="pt-2 border-t border-fantasy-border/30 space-y-1.5">
                              <span className="text-xs font-bold text-amber-400 uppercase tracking-wider block">
                                ⚔️ Rivals
                              </span>
                              {rivalsList.length > 0 ? (
                                <div className="space-y-1">
                                  {rivalsList.map((r, i) => (
                                    <div key={i} className="text-amber-300 font-medium">
                                      • ⚔️ {renderLinkedPerson(r, 'text-amber-300 font-medium')}
                                    </div>
                                  ))}
                                </div>
                              ) : (
                                <p className="text-gray-500 italic text-xs">No known rivals recorded.</p>
                              )}
                            </div>

                            <div className="text-[11px] text-gray-500 font-mono pt-1.5 border-t border-fantasy-border/20">
                              Information Disclosure Level: {infoLevel}/3 • Social Graph & Lineage Dossier{isDebugRevealed ? ' • [🛠️ DEBUG: Revealed]' : ''}
                            </div>
                          </div>
                        );
                      })()}

                      {/* SUBTAB 4: INTIMATE & HISTORY */}
                      {contactTab === 'intimate' && (() => {
                        const intSec = npc.intimate_sections || {};
                        const hasSections = Boolean(intSec.anatomy && intSec.dynamic);

                        const rawGen = (basic.gender || npc.gender || '').toLowerCase();
                        const isMaleNpc = ['male', 'man', 'boy', 'lord', 'he', 'him', 'his'].some(kw => rawGen.includes(kw)) && !['female', 'woman', 'girl', 'lady'].some(kw => rawGen.includes(kw));
                        const bSize = (appearance.breast_size || 'Modest B-Cup');
                        const bTitle = bSize.charAt(0).toUpperCase() + bSize.slice(1);
                        const pSize = (appearance.penis_size || 'Average');
                        const pTitle = pSize.charAt(0).toUpperCase() + pSize.slice(1);
                        const sizeDisplay = isMaleNpc ? ((infoLevel >= 3 || isDebugRevealed) ? pTitle : 'Unknown') : bTitle;

                        const iExpDisp = (appearance.experience && appearance.experience.toLowerCase() !== 'unknown') ? appearance.experience : (infoLevel >= 3 || isDebugRevealed ? (appearance.intercourse_experience === 'virgin' ? 'Virgin' : 'Non-Virgin') : 'Unknown');
                        const oExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.oral_experience || 'Inexperienced') : 'Unknown';
                        const mExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.manual_experience || 'Inexperienced') : 'Unknown';
                        const aExpDisp = (infoLevel >= 3 || isDebugRevealed) ? (appearance.anal_experience || 'Inexperienced') : 'Unknown';

                        const underObj = typeof appearance.undergarments === 'object' && appearance.undergarments !== null ? appearance.undergarments : {};
                        const rawBra = underObj.bra || appearance.bra || (typeof appearance.undergarments === 'string' && appearance.undergarments.includes('Bra:') ? appearance.undergarments.split('•')[0]?.replace('Bra:', '').trim() : '');
                        const rawUnd = underObj.underwear || appearance.underwear || (typeof appearance.undergarments === 'string' && appearance.undergarments.includes('Underwear:') ? appearance.undergarments.split('•')[1]?.replace('Underwear:', '').trim() : (typeof appearance.undergarments === 'string' ? appearance.undergarments : ''));
                        const braVal = rawBra ? rawBra.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone') : '';
                        const undVal = rawUnd ? rawUnd.replace(/\bNude\s*\/\s*Beige\b/gi, 'Beige / Skin-Tone') : '';

                        const isHistoryUnlocked = infoLevel >= 3 || Boolean(npc.history_revealed) || isDebugRevealed;
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
                            <div>
                              <span className="text-xs font-bold text-pink-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                🔞 Anatomy & Experience
                              </span>
                              {hasSections && intSec.anatomy ? (
                                renderBulletPoints(intSec.anatomy.map(line => {
                                  if (!isMaleNpc && /breast size.*unknown/i.test(line) && bTitle) {
                                    return `• **Breast Size**: ${bTitle}`;
                                  }
                                  return line;
                                }))
                              ) : (
                                <div className="space-y-1 text-gray-300 leading-relaxed">
                                  <div>• <strong className="text-gray-100">{isMaleNpc ? 'Penis Size' : 'Breast Size'}</strong>: {sizeDisplay}</div>
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

                            <div className="pt-2 border-t border-fantasy-border/30">
                              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider block mb-1.5 flex items-center gap-1.5">
                                🩲 Undergarments
                              </span>
                              {hasSections && intSec.undergarments ? (
                                renderBulletPoints(intSec.undergarments)
                              ) : (
                                <div className="space-y-1 text-gray-300 leading-relaxed">
                                  {!isMaleNpc && (
                                    <div>• <strong className="text-gray-100">Bra</strong>: {(infoLevel >= 3 || isDebugRevealed) && braVal ? braVal : <span className="text-gray-500 italic">Unknown</span>}</div>
                                  )}
                                  <div>• <strong className="text-gray-100">Underwear</strong>: {(infoLevel >= 3 || isDebugRevealed) && undVal ? undVal : <span className="text-gray-500 italic">Unknown</span>}</div>
                                </div>
                              )}
                            </div>

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

                            <div className="pt-2 border-t border-fantasy-border/30 space-y-1">
                              <span className="text-xs font-bold text-gray-300 uppercase tracking-wider block mb-0.5">
                                Past Intimate History
                              </span>
                              {!isHistoryUnlocked ? (
                                <p className="text-gray-500 italic text-xs leading-relaxed">
                                  🔒 Locked — Requires Confidant / Soulmate standing (Info Level 3/3) to uncover.
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

                            <div className="text-[11px] text-gray-500 font-mono pt-1.5 border-t border-fantasy-border/20">
                              Information Disclosure Level: {infoLevel}/3 • Intimate Dossier{isDebugRevealed ? ' • [🛠️ DEBUG: Revealed]' : ''}
                            </div>
                          </div>
                        );
                      })()}
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default ContactsPanel;
