import { useState, useEffect, useMemo, useRef, useId } from 'react';
import { useTranslation } from 'react-i18next';
import {
  BookOpen,
  Calendar,
  Flag,
  Globe,
  Scroll,
  Search,
  Users,
} from 'lucide-react';
import { apiCall } from '../../api/client';
import { useUiPreferences } from '../../theme/UiPreferencesProvider';
import { formatScenarioCurrency } from '../../utils/currency';
import { isAnomalousScenarioKey } from '../../utils/session';
import { defaultBulletRenderer, formatPersonEntity } from './NpcDossierBody';
import CodexCharactersTab, {
  getRelationshipTier,
  getStandingBadgeClass,
} from './CodexCharactersTab';
import CodexFactionsTab, {
  getFactionCategoryBadge,
  getReputationTier,
} from './CodexFactionsTab';
import CodexLoreTab from './CodexLoreTab';
import CodexAgendaTab from './CodexAgendaTab';

export {
  getStandingBadgeClass,
  getRelationshipTier,
  getFactionCategoryBadge,
  getReputationTier,
};

const renderBulletPoints = (lines, t = null) => defaultBulletRenderer(lines, t);

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
  onConsumeTargetContact = null,
  onJumpToSavedContact,
  isStreaming = false,
  processingTurn = false,
}) => {
  const { t } = useTranslation();
  const { clockFormat } = useUiPreferences();
  const {
    contacts = [],
    factions = [],
    agentDossier,
    lorebook = {},
    worldPulse,
    commitments = [],
    encyclopedia,
    loading,
    factionHqAction,
    refreshCodex,
    cancelCommitment,
    trackRumor,
  } = codexHook || {};
  const isAnomalousScenario = isAnomalousScenarioKey(session?.scenario);
  const calibCost = formatScenarioCurrency(500, session?.scenario || 'anomalous_incursions');
  const [subTab, setSubTab] = useState('contacts'); // 'contacts' | 'factions' | 'lore' | 'agenda' | 'encyclopedia'

  useEffect(() => {
    if (!isAnomalousScenario && subTab === 'encyclopedia') {
      setSubTab('contacts');
    }
  }, [isAnomalousScenario, subTab]);

  const [searchQuery, setSearchQuery] = useState('');
  const [expandedNpc, setExpandedNpc] = useState(null);
  const [highlightedNpcKey, setHighlightedNpcKey] = useState(null);
  const [debugDossierTab, setDebugDossierTab] = useState('persona');
  const [expandedFaction, setExpandedFaction] = useState(null);
  const [factionDomainFilter, setFactionDomainFilter] = useState('all'); // 'all' | 'school' | 'regular'
  const [companionBusy, setCompanionBusy] = useState(null);
  const [factionBusy, setFactionBusy] = useState(null);
  const [cancellingCommitmentId, setCancellingCommitmentId] = useState(null);
  const [companionFeedback, setCompanionFeedback] = useState(null);
  const [busyRumorId, setBusyRumorId] = useState(null);
  const calibId = useId();
  const agentAxis3 = agentDossier?.character_3axis;
  const playerAxis3 = session?.player_3axis;
  const [calAttr, setCalAttr] = useState(playerAxis3?.attribute || 'fire');
  const [calArch, setCalArch] = useState(playerAxis3?.combat_archetype || 'vanguard');
  const [calMed, setCalMed] = useState(playerAxis3?.ability_medium || 'direct_manifestation');

  useEffect(() => {
    const src3 = agentAxis3 || playerAxis3;
    if (src3?.attribute) setCalAttr(src3.attribute);
    if (src3?.combat_archetype) setCalArch(src3.combat_archetype);
    if (src3?.ability_medium) setCalMed(src3.ability_medium);
  }, [agentAxis3, playerAxis3]);

  const handleTrackRumor = async (eventKey) => {
    if (!eventKey || !trackRumor || busyRumorId) return;
    setBusyRumorId(eventKey);
    setCompanionFeedback(null);
    try {
      const data = await trackRumor(eventKey);
      if (data?.world_pulse && onSessionUpdated && session) {
        onSessionUpdated({ ...session, world_pulse: data.world_pulse });
      }
      setCompanionFeedback({
        type: 'ok',
        text: data?.quest?.title ? `Tracking lead: ${data.quest.title}` : 'Rumor investigation started.',
      });
    } catch (err) {
      setCompanionFeedback({ type: 'error', text: err.message || 'Could not track rumor.' });
    } finally {
      setBusyRumorId(null);
    }
  };

  const cardRefs = useRef({});
  const partyNpcNames = new Set(
    (session?.party_npcs || []).map(p => (p.name || '').toLowerCase())
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

  const handleFactionOp = async (factionId, action, extraPayload = {}) => {
    if (!factionHqAction || factionBusy) return;
    setFactionBusy(`${factionId}:${action}`);
    setCompanionFeedback(null);
    try {
      const data = await factionHqAction(factionId, action, extraPayload);
      if (data?.message) {
        setCompanionFeedback({ type: 'ok', text: data.message });
      }
      if (action === 'calibrate' && data && onSessionUpdated) {
        onSessionUpdated({
          ...session,
          player_3axis: {
            attribute: data.attribute,
            combat_archetype: data.combat_archetype,
            ability_medium: data.ability_medium,
          },
          telemetry_calibrations_used: data.telemetry_calibrations_used ?? session?.telemetry_calibrations_used,
        });
      }
      if ((action === 'rest' || action === 'calibrate' || action === 'join' || action === 'transfer' || action === 'leave') && onRefreshCharacter) {
        onRefreshCharacter();
      }
      if ((action === 'join' || action === 'transfer' || action === 'leave') && data) {
        if (refreshCodex) refreshCodex();
        if (data.session_sync && onSessionUpdated) {
          onSessionUpdated({ ...session, ...data.session_sync });
        }
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

  const lastHandledTargetPulseRef = useRef(0);
  const targetScrollTimerRef = useRef(null);
  const targetHighlightTimerRef = useRef(null);

  useEffect(() => () => {
    clearTimeout(targetScrollTimerRef.current);
    clearTimeout(targetHighlightTimerRef.current);
  }, []);

  useEffect(() => {
    if (!targetContactName || targetContactPulse === lastHandledTargetPulseRef.current) return undefined;
    const targetLow = String(targetContactName ?? '').trim().toLowerCase();
    const matched = knownCharacters.find(c =>
      String(c.name ?? '').trim().toLowerCase() === targetLow ||
      String(c.id ?? '').trim().toLowerCase() === targetLow ||
      String(c.npc_id ?? '').trim().toLowerCase() === targetLow
    );
    if (!matched && loading) return undefined;
    lastHandledTargetPulseRef.current = targetContactPulse;
    setSubTab('contacts');
    setSearchQuery('');
    const key = matched ? (matched.id || matched.name) : targetContactName;
    setExpandedNpc(key);
    setHighlightedNpcKey(key);
    clearTimeout(targetScrollTimerRef.current);
    clearTimeout(targetHighlightTimerRef.current);
    targetScrollTimerRef.current = setTimeout(() => {
      const el = cardRefs.current[key] || (matched?.name && cardRefs.current[String(matched.name).toLowerCase()]) || cardRefs.current[targetLow];
      if (el && typeof el.scrollIntoView === 'function') {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }, 80);
    targetHighlightTimerRef.current = setTimeout(() => setHighlightedNpcKey(null), 2400);
    onConsumeTargetContact?.();
    return undefined;
  }, [targetContactName, targetContactPulse, knownCharacters, loading, onConsumeTargetContact]);

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

  const filteredFactions = factions.filter(f => {
    const q = searchQuery.toLowerCase();
    const name = (f.name || f.faction_id || '').toLowerCase();
    const desc = (f.description || f.notes || '').toLowerCase();
    if (!name.includes(q) && !desc.includes(q)) return false;
    if (factionDomainFilter === 'school') {
      return Boolean(f.is_school_club || f.category_tag?.domain === 'school');
    }
    if (factionDomainFilter === 'regular') {
      return !(f.is_school_club || f.category_tag?.domain === 'school');
    }
    return true;
  });

  const hasSchoolFactions = factions.some(f => Boolean(f.is_school_club || f.category_tag?.domain === 'school'));
  const hasRegularFactions = factions.some(f => !(f.is_school_club || f.category_tag?.domain === 'school'));

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
    <div className="space-y-3 min-h-full flex-1 flex flex-col min-w-0">
      <div className="space-y-2 border-b border-fantasy-border/35 pb-2.5">
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
              : subTab === 'encyclopedia'
              ? `[${encyclopedia?.discovered_count ?? 0}/${encyclopedia?.total_folklore_count ?? 50}]`
              : t('codex.lore_count', { count: filteredLore.length, defaultValue: `${filteredLore.length} Lore` })}
          </span>
        </div>

        <div className="flex flex-wrap gap-1">
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

          {isAnomalousScenario && (
            <button
              onClick={() => { setSubTab('encyclopedia'); setSearchQuery(''); }}
              className={`flex-1 flex items-center justify-center gap-1.5 py-1 rounded text-[11px] font-semibold uppercase tracking-wider transition-colors ${
                subTab === 'encyclopedia'
                  ? 'bg-amber-950/60 text-amber-300 border border-amber-600/50'
                  : 'text-gray-400 hover:text-gray-200'
              }`}
            >
              <Scroll size={11} />
              <span>{t('codex.encyclopedia', 'Encyclopedia')}</span>
            </button>
          )}
        </div>

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

      {loading && contacts.length === 0 ? (
        <p className="text-xs text-gray-500 italic text-center py-8">{t('codex.loading_archives', 'Consulting codex archives...')}</p>
      ) : (
        <div className="space-y-3 flex-1 flex flex-col">
          {subTab === 'contacts' && (
            <CodexCharactersTab
              filteredContacts={filteredContacts}
              session={session}
              partyNpcNames={partyNpcNames}
              expandedNpc={expandedNpc}
              onToggleNpc={setExpandedNpc}
              highlightedNpcKey={highlightedNpcKey}
              cardRefs={cardRefs}
              debugDossierTab={debugDossierTab}
              onChangeDebugDossierTab={setDebugDossierTab}
              companionBusy={companionBusy}
              onToggleCompanion={handleToggleCompanion}
              onJumpToSavedContact={onJumpToSavedContact}
              renderLinkedPerson={renderLinkedPerson}
              renderBulletPoints={renderBulletPoints}
              t={t}
            />
          )}

          {subTab === 'factions' && (
            <CodexFactionsTab
              factions={factions}
              filteredFactions={filteredFactions}
              hasSchoolFactions={hasSchoolFactions}
              hasRegularFactions={hasRegularFactions}
              factionDomainFilter={factionDomainFilter}
              onChangeFactionDomainFilter={setFactionDomainFilter}
              expandedFaction={expandedFaction}
              onToggleFaction={setExpandedFaction}
              session={session}
              agentDossier={agentDossier}
              factionBusy={factionBusy}
              onFactionOp={handleFactionOp}
              calibId={calibId}
              calibCost={calibCost}
              calAttr={calAttr}
              setCalAttr={setCalAttr}
              calArch={calArch}
              setCalArch={setCalArch}
              calMed={calMed}
              setCalMed={setCalMed}
              t={t}
            />
          )}

          {(subTab === 'lore' || subTab === 'encyclopedia') && (
            <CodexLoreTab
              subTab={subTab}
              worldPulse={worldPulse}
              filteredLore={filteredLore}
              searchQuery={searchQuery}
              busyRumorId={busyRumorId}
              onTrackRumor={handleTrackRumor}
              isStreaming={isStreaming}
              processingTurn={processingTurn}
              session={session}
              encyclopedia={encyclopedia}
            />
          )}

          {subTab === 'agenda' && (
            <CodexAgendaTab
              filteredCommitments={filteredCommitments}
              clockFormat={clockFormat}
              cancellingCommitmentId={cancellingCommitmentId}
              onCancelAgendaItem={handleCancelAgendaItem}
              findDiscoveredContact={findDiscoveredContact}
              onJumpToContact={jumpToContact}
              t={t}
            />
          )}
        </div>
      )}
    </div>
  );
};

export default CodexPanel;
