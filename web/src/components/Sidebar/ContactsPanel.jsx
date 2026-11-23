import { useState, useEffect, useMemo, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import {
  Smartphone, Users, Heart, Search, MessageCircle, MapPin, Lock,
  ChevronDown, ChevronRight, User, UserPlus, UserMinus, ShieldAlert
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { StatusEffectBadge } from './CharacterSheet';
import { getRelationshipTier } from './CodexPanel';
import { formatCleanLocation } from '../../utils/locationFormat';
import AcquaintancesView from './AcquaintancesView';
import NpcDossierBody, {
  defaultBulletRenderer as renderBulletPoints,
  formatPersonEntity,
  resolveAffiliations,
  resolveAgeGroupLabel,
} from './NpcDossierBody';
import {
  formatGender,
  formatRace,
  formatTitle,
} from '../../utils/npcDemographics';
import {
  findLinkedPersonInRoster,
  unwrapDebugProfile,
} from '../../utils/npcProfile';

export { renderBulletPoints };

const ContactsPanel = ({
  codexHook,
  session,
  user,
  onSessionUpdated,
  onMessageContact,
  onJumpToCharacterInCodex,
  targetContactName,
  targetContactPulse,
  onConsumeTargetContact = null,
}) => {
  const { t } = useTranslation();
  const { contacts = [], acquaintances = [], lorebook = {}, loading } = codexHook || {};
  const [activeSubTab, setActiveSubTab] = useState('contacts');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNpc, setExpandedNpc] = useState(null);
  const [highlightedNpcKey, setHighlightedNpcKey] = useState(null);
  const [contactTab, setContactTab] = useState('persona');
  const [companionBusy, setCompanionBusy] = useState(null);
  const [companionFeedback, setCompanionFeedback] = useState(null);
  const cardRefs = useRef({});
  const lastHandledTargetPulseRef = useRef(0);
  const scrollTimerRef = useRef(null);
  const highlightTimerRef = useRef(null);

  useEffect(() => () => {
    clearTimeout(scrollTimerRef.current);
    clearTimeout(highlightTimerRef.current);
  }, []);

  const personalContacts = useMemo(
    () => (contacts || []).filter(c => !c.is_dispatch_channel),
    [contacts]
  );

  useEffect(() => {
    if (!targetContactName || targetContactPulse === lastHandledTargetPulseRef.current) return undefined;
    const targetLow = String(targetContactName ?? '').trim().toLowerCase();
    const matched = personalContacts.find(c =>
      String(c.name ?? '').trim().toLowerCase() === targetLow ||
      String(c.id ?? '').trim().toLowerCase() === targetLow ||
      String(c.npc_id ?? '').trim().toLowerCase() === targetLow
    );
    if (matched) {
      lastHandledTargetPulseRef.current = targetContactPulse;
      setSearchQuery('');
      setActiveSubTab('contacts');
      setContactTab('persona');
      const key = matched.id || matched.name;
      setExpandedNpc(key);
      setHighlightedNpcKey(key);
      clearTimeout(scrollTimerRef.current);
      clearTimeout(highlightTimerRef.current);
      scrollTimerRef.current = setTimeout(() => {
        const el = cardRefs.current[key] || cardRefs.current[String(matched.name ?? '').toLowerCase()];
        if (el && typeof el.scrollIntoView === 'function') {
          el.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
      }, 80);
      highlightTimerRef.current = setTimeout(() => setHighlightedNpcKey(null), 2400);
      onConsumeTargetContact?.();
      return undefined;
    }
    const acqList = Array.isArray(acquaintances) ? acquaintances : [];
    const matchedAcq = acqList.find(a =>
      String(a.name ?? '').trim().toLowerCase() === targetLow ||
      String(a.id ?? '').trim().toLowerCase() === targetLow ||
      String(a.npc_id ?? '').trim().toLowerCase() === targetLow ||
      String(a.npc_key ?? '').trim().toLowerCase() === targetLow
    );
    if (matchedAcq) {
      lastHandledTargetPulseRef.current = targetContactPulse;
      setSearchQuery('');
      setActiveSubTab('acquaintances');
      return undefined;
    }
    if (!loading) {
      lastHandledTargetPulseRef.current = targetContactPulse;
      onConsumeTargetContact?.();
    }
    return undefined;
  }, [targetContactName, targetContactPulse, personalContacts, acquaintances, loading, onConsumeTargetContact]);

  const partyNpcNames = useMemo(
    () => new Set((session?.party_npcs || []).map(p => (p.name || '').toLowerCase())),
    [session?.party_npcs]
  );

  const handleToggleCompanion = async (npcName, isInParty) => {
    if (!session?.id || !user?.user_id) return;
    setCompanionBusy(npcName);
    setCompanionFeedback(null);
    try {
      const data = await apiCall('/api/party/companion', {
        method: 'POST',
        body: JSON.stringify({
          user_id: user.user_id,
          session_id: session.id,
          npc_name: npcName,
          action: isInParty ? 'dismiss' : 'recruit',
        }),
      });
      setCompanionFeedback({ type: 'ok', text: data.message || 'Party updated.' });
      if (onSessionUpdated && Array.isArray(data.party_npcs)) {
        onSessionUpdated({ ...session, party_npcs: data.party_npcs });
      }
    } catch (err) {
      setCompanionFeedback({ type: 'error', text: err.message || 'Could not update party.' });
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

  const filteredAcquaintances = useMemo(() => {
    const list = Array.isArray(acquaintances) ? acquaintances : [];
    const q = searchQuery.toLowerCase().trim();
    if (!q) return list;
    return list.filter(a => {
      const name = (a.name || '').toLowerCase();
      const role = (a.public_role || a.basic_info?.role || a.role || '').toLowerCase();
      const workplace = (a.workplace_label || '').toLowerCase();
      const origin = (a.origin || '').toLowerCase();
      const faction = (a.faction_affiliation || a.basic_info?.faction || a.faction || '').toLowerCase();
      const anomTag = (a.anomalous_tag_label || a.anomalous_npc_tag || a.basic_info?.anomalous_npc_tag || '').toLowerCase();
      return name.includes(q) || role.includes(q) || workplace.includes(q) || origin.includes(q) || faction.includes(q) || anomTag.includes(q);
    });
  }, [acquaintances, searchQuery]);

  const findLinkedPerson = (itemOrName) =>
    findLinkedPersonInRoster(itemOrName, personalContacts, lorebook?.entities || []);

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

  return (
    <div className="space-y-3 min-h-full flex-1 flex flex-col min-w-0">
      {/* Header & Search */}
      <div className="space-y-2 border-b border-fantasy-border/35 pb-2.5">
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <Smartphone size={16} className="text-fantasy-accent shrink-0" />
            <h3 className="font-rpg font-bold text-xs sm:text-sm text-gray-100 uppercase tracking-wider truncate">
              {activeSubTab === 'acquaintances'
                ? t('contacts.tab_acquaintances', 'Acquaintances')
                : t('contacts.title', 'Contacts')}
            </h3>
          </div>
          <span className="text-[10px] font-mono text-gray-400 shrink-0">
            {activeSubTab === 'acquaintances'
              ? t('contacts.acquaintances_count', { count: filteredAcquaintances.length, defaultValue: `${filteredAcquaintances.length} Met` })
              : t('contacts.count', { count: filteredContacts.length, defaultValue: `${filteredContacts.length} Saved` })}
          </span>
        </div>

        {/* Contacts | Acquaintances Segmented Toggle */}
        <div
          role="tablist"
          aria-label={t('contacts.title', 'Contacts')}
          className="grid grid-cols-2 gap-1"
        >
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'contacts'}
            onClick={() => setActiveSubTab('contacts')}
            className={`py-1 px-2 rounded text-[11px] font-bold transition-all cursor-pointer truncate ${
              activeSubTab === 'contacts'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 border border-transparent'
            }`}
          >
            {t('contacts.tab_contacts', 'Contacts')} ({filteredContacts.length})
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={activeSubTab === 'acquaintances'}
            onClick={() => setActiveSubTab('acquaintances')}
            className={`py-1 px-2 rounded text-[11px] font-bold transition-all cursor-pointer truncate ${
              activeSubTab === 'acquaintances'
                ? 'bg-fantasy-accent/20 text-fantasy-accent border border-fantasy-accent/40 shadow-sm'
                : 'text-gray-400 hover:text-gray-200 border border-transparent'
            }`}
          >
            {t('contacts.tab_acquaintances', 'Acquaintances')} ({filteredAcquaintances.length})
          </button>
        </div>

        <div className="relative">
          <Search size={12} className="absolute left-2.5 top-2 text-gray-500" />
          <input
            type="text"
            aria-label={
              activeSubTab === 'acquaintances'
                ? t('contacts.search_acquaintances', 'Search Acquaintances...')
                : t('contacts.search_placeholder', 'Search Contacts...')
            }
            placeholder={
              activeSubTab === 'acquaintances'
                ? t('contacts.search_acquaintances', 'Search Acquaintances...')
                : t('contacts.search_placeholder', 'Search Contacts...')
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
      {activeSubTab === 'acquaintances' ? (
        <AcquaintancesView
          acquaintances={filteredAcquaintances}
          loading={loading}
          searchQuery={searchQuery}
          onMessageContact={onMessageContact}
          targetAcquaintanceName={targetContactName}
          targetAcquaintancePulse={targetContactPulse}
          onConsumeTargetContact={onConsumeTargetContact}
          t={t}
        />
      ) : loading && personalContacts.length === 0 ? (
        <p className="text-xs text-gray-500 italic text-center py-8">{t('contacts.loading', 'Loading saved contacts...')}</p>
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
            const npc = unwrapDebugProfile(rawNpc);
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


            return (
              <div
                key={npcToggleKey}
                ref={(el) => {
                  cardRefs.current[npcToggleKey] = el;
                  if (npc.name) cardRefs.current[String(npc.name).toLowerCase()] = el;
                }}
                className={`bg-black/50 border rounded-lg p-2.5 space-y-1.5 transition-all ${
                  highlightedNpcKey === npcToggleKey
                    ? 'border-fantasy-accent ring-2 ring-fantasy-accent/60 shadow-lg shadow-fantasy-accent/20'
                    : isBlocked
                      ? 'border-red-900/60 hover:border-red-700/70'
                      : 'border-fantasy-border/60 hover:border-fantasy-border'
                }`}
              >
                {/* Header Toggle Button */}
                <button
                  type="button"
                  aria-expanded={isExpanded}
                  onClick={() => {
                    if (!isExpanded) setContactTab('persona');
                    setExpandedNpc(isExpanded ? null : npcToggleKey);
                  }}
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
                          <span className="text-[9px] px-1.5 py-0.5 bg-red-950/80 text-red-300 rounded font-bold uppercase border border-red-700/60">
                            🚫 {t('contacts.blocked_badge', 'Blocked')}
                          </span>
                        )}
                        {isSpecialAgent && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-cyan-950/70 text-cyan-300 rounded font-bold uppercase border border-cyan-700/50">
                            ⚡ {t('codex.special_agent', 'Special Agent')}
                          </span>
                        )}
                        {isCivilianTag && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-slate-900/80 text-slate-300 rounded font-semibold uppercase border border-slate-700/60">
                            {t('codex.civilian', 'Civilian')}
                          </span>
                        )}
                        {isDeceased && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-rose-950/80 text-rose-300 rounded font-bold uppercase border border-rose-700/60">
                            💀 {t('codex.deceased', 'Deceased')}
                          </span>
                        )}
                        {isInParty && (
                          <span className="text-[9px] px-1.5 py-0.5 bg-purple-950/60 text-purple-300 rounded font-bold uppercase border border-purple-800/40">
                            {t('codex.in_party', 'In Party')}
                          </span>
                        )}
                        {isRomantic && (
                          <span className="text-[9px] px-1 py-0.5 bg-pink-950/60 text-pink-300 rounded font-bold uppercase border border-pink-800/40">
                            {t('codex.romantic', 'Romantic')}
                          </span>
                        )}
                        {npc.clothing_status && (
                          <span className="text-[8.5px] font-mono px-1 py-0.5 rounded bg-black/60 text-gray-300 border border-neutral-700/60 leading-tight">
                            {npc.clothing_status}
                          </span>
                        )}
                      </div>
                      <span className="text-[11px] text-gray-400 font-medium block truncate max-w-56">
                        {npc.public_role || basic.public_role || basic.role || basic.occupation || (basic.faction ? `${basic.faction} Member` : 'Contact')}
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
                    {(() => {
                      const { isStudent, club, faction } = resolveAffiliations(npc, basic);
                      const ageLabel = resolveAgeGroupLabel(npc, basic, isStudent, t);
                      const genderInfo = formatGender(basic.gender || npc.gender, t);
                      const raceLabel = formatRace(basic.race || npc.race, t);
                      return (
                        <>
                          {ageLabel && (
                            <span className="px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 border border-amber-800/40 text-[10.5px]">
                              {ageLabel}
                            </span>
                          )}
                          {club && (
                            <span className="px-1.5 py-0.5 rounded bg-cyan-950/40 text-cyan-300 border border-cyan-800/40 text-[10.5px]">
                              Club: {formatTitle(club)}
                            </span>
                          )}
                          {faction && (
                            <span className="px-1.5 py-0.5 rounded bg-slate-900/60 text-slate-300 border border-slate-700/50 text-[10.5px]">
                              Faction: {formatTitle(faction)}
                            </span>
                          )}
                          {raceLabel && (
                            <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                              {raceLabel}
                            </span>
                          )}
                          {genderInfo && (
                            <span className="px-1.5 py-0.5 rounded bg-black/60 text-gray-300 border border-fantasy-border/40 text-[10.5px]">
                              {genderInfo.symbol ? `${genderInfo.symbol} ` : ''}{genderInfo.label}
                            </span>
                          )}
                        </>
                      );
                    })()}
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
                      {onMessageContact && (() => {
                        const isDmLocked = npc.can_dm === false;
                        const cannotDm = isBlocked || isDeceased || isDmLocked;
                        return (
                          <button
                            type="button"
                            disabled={cannotDm}
                            onClick={(e) => {
                              e.stopPropagation();
                              if (!cannotDm) onMessageContact(npc);
                            }}
                            title={
                              isDeceased
                                ? t('codex.deceased', 'Deceased')
                                : isBlocked
                                  ? t('phone.blocked_notice', 'This contact has blocked your number due to hostility. Reconcile with them in person first.')
                                  : isDmLocked
                                    ? t('contacts.dm_locked_tooltip', 'Direct Messaging is locked. Ask for their number in person or connect via PeerPulse first; Affinity alone does not unlock DMs.')
                                    : `${t('contacts.message_btn', 'Message')} ${npc.name}`
                            }
                            className={`flex items-center gap-1 py-1 px-2.5 rounded text-[11px] font-bold border transition-all select-none focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-cyan-400 ${
                              cannotDm
                                ? 'opacity-45 cursor-not-allowed bg-neutral-900/60 border-neutral-700/50 text-gray-500'
                                : 'bg-cyan-950/50 hover:bg-cyan-900/60 border-cyan-700/60 text-cyan-200 cursor-pointer'
                            }`}
                          >
                            {isDmLocked && !isBlocked && !isDeceased ? <Lock size={12} /> : <MessageCircle size={12} />}
                            <span>
                              {isBlocked
                                ? t('contacts.blocked_badge', 'Blocked')
                                : isDmLocked
                                  ? t('contacts.dm_locked_badge', 'DM Locked')
                                  : t('contacts.message_btn', 'Message')}
                            </span>
                          </button>
                        );
                      })()}
                    </div>
                  </div>
                </div>

                {/* Expanded Full Personal Dossier */}
                {isExpanded && (
                  <NpcDossierBody
                    npc={npc}
                    npcKey={npcToggleKey}
                    session={session}
                    t={t}
                    isBlocked={isBlocked}
                    isDeceased={isDeceased}
                    isInParty={isInParty}
                    isSpecialAgent={isSpecialAgent}
                    isCivilianTag={isCivilianTag}
                    isDebugRevealed={isDebugRevealed}
                    sourceKind="contact"
                    activeTab={contactTab}
                    onTabChange={setContactTab}
                    topSlot={
                      isInParty ? (
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
                      ) : isSpecialAgent ? (
                        <div className="flex items-center justify-between bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40">
                          <span className="text-xs text-gray-300">
                            {t('codex.recruit_desc', 'Invite this operative to join your strike team.')}
                          </span>
                          <button
                            type="button"
                            disabled={companionBusy === npc.name}
                            onClick={(e) => {
                              e.stopPropagation();
                              handleToggleCompanion(npc.name, false);
                            }}
                            className="flex items-center gap-1.5 px-3 py-1.5 rounded text-xs font-bold border transition-all shrink-0 bg-emerald-950/50 border-emerald-800/60 text-emerald-300 hover:bg-emerald-900/60 cursor-pointer"
                          >
                            <UserPlus size={13} />
                            <span>{companionBusy === npc.name ? '...' : t('codex.recruit', 'Recruit')}</span>
                          </button>
                        </div>
                      ) : null
                    }
                    renderBulletPoints={renderBulletPoints}
                    findLinkedPerson={findLinkedPerson}
                    renderLinkedPerson={renderLinkedPerson}
                    onJumpToPerson={handleJumpToPerson}
                  />
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
