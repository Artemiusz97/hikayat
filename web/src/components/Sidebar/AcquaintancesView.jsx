import { useState } from 'react';
import {
  Briefcase,
  ChevronDown,
  ChevronRight,
  Lock,
  MessageCircle,
  Sparkles,
  User,
  Users,
} from 'lucide-react';
import { getRelationshipTier } from './CodexPanel';
import KnownRoutineCard from './KnownRoutineCard';
import KnownWardrobeCard from './KnownWardrobeCard';

const formatItemText = (item) => {
  if (!item) return '';
  if (typeof item === 'string') return item;
  return item.trait || item.name || item.label || '';
};

const AcquaintancesView = ({ acquaintances = [], loading = false, searchQuery = '', t }) => {
  const [expandedKey, setExpandedKey] = useState(null);

  if (loading && acquaintances.length === 0) {
    return (
      <p className="text-xs text-gray-500 italic text-center py-8">
        {t('contacts.loading', 'Loading saved contacts...')}
      </p>
    );
  }

  const hasSearch = Boolean(String(searchQuery || '').trim());
  if (acquaintances.length === 0) {
    return (
      <div className="text-center py-8 px-3 text-gray-500 border border-dashed border-fantasy-border/50 rounded-md">
        <Users size={24} className="mx-auto mb-1.5 opacity-40" />
        <p className="text-xs">
          {hasSearch
            ? t('contacts.no_acquaintances_match', 'No matching acquaintances found.')
            : t('contacts.no_acquaintances', 'No met acquaintances yet.')}
        </p>
        {!hasSearch && (
          <p className="text-[10px] text-gray-500 mt-1 leading-relaxed">
            {t(
              'contacts.acquaintances_hint',
              'Characters you briefly meet or converse with appear here until your bond deepens enough for Saved Contacts.'
            )}
          </p>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-3 flex-1 flex flex-col">
      {acquaintances.map((acq) => {
        const cardKey = acq.npc_key || acq.npc_id || acq.id || acq.name;
        const isExpanded = expandedKey === cardKey;
        const score = acq.affinity_score ?? acq.relationship_score ?? 0;
        const isRomantic = (acq.track === 'romantic') || (acq.relations?.track === 'romantic');
        const tier = getRelationshipTier(score, isRomantic ? 'romantic' : 'platonic', t);
        const roleLabel = acq.public_role || acq.role || acq.basic_info?.role || '';
        const workplaceLabel = acq.workplace_label || '';
        const traits = acq.unlocked_traits || acq.traits || [];
        const likes = acq.preferences || [];
        const dislikes = acq.dislikes || [];
        const basic = acq.basic_info || {};
        const desc = basic.description || acq.appearance?.summary || acq.description || '';
        const isDmLocked = acq.can_dm === false;
        const maskedSlot = t('social.masked_slot', '???');

        return (
          <div
            key={cardKey}
            className="bg-black/50 border border-fantasy-border rounded-lg p-3 space-y-2.5 transition-all hover:border-fantasy-accent/30"
          >
            <div
              role="button"
              tabIndex={0}
              aria-expanded={isExpanded}
              onClick={() => setExpandedKey(isExpanded ? null : cardKey)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  setExpandedKey(isExpanded ? null : cardKey);
                }
              }}
              className="flex flex-col gap-2 cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-fantasy-accent rounded"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-start gap-2.5 min-w-0">
                  <div className="w-8 h-8 rounded-full bg-fantasy-panel/90 border border-fantasy-border/80 flex items-center justify-center text-gray-300 shrink-0 mt-0.5">
                    <User size={15} />
                  </div>
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="font-bold text-sm text-gray-100 leading-tight truncate">
                        {acq.name}
                      </span>
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800/90 text-slate-300 border border-slate-600/60 font-semibold">
                        {t('contacts.acquaintance_badge', 'Acquaintance')}
                      </span>
                      {acq.origin && (
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-black/60 text-gray-400 border border-fantasy-border/50 font-mono">
                          {String(acq.origin).replace(/_/g, ' ')}
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-1.5 text-[11px] text-gray-400">
                      {roleLabel && <span>{roleLabel}</span>}
                      {roleLabel && workplaceLabel && <span aria-hidden="true">•</span>}
                      {workplaceLabel && (
                        <span className="inline-flex items-center gap-1 text-emerald-300/85">
                          <Briefcase size={10} className="shrink-0" />
                          <span>{workplaceLabel}</span>
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                <div className="flex flex-col items-end gap-1 shrink-0">
                  <span className={`text-[11px] font-bold ${tier.color}`}>
                    {tier.label}
                  </span>
                  <span className="text-[10px] font-mono text-gray-400">
                    {score >= 0 ? `+${score}` : score}
                  </span>
                </div>
              </div>

              <div className="flex flex-wrap items-center justify-between gap-2 pt-1 border-t border-fantasy-border/30">
                <div className="inline-flex items-center gap-1 text-[11px] text-gray-400">
                  {isExpanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
                  <span>
                    {isExpanded
                      ? t('codex.view_summary', 'Summary View')
                      : t('codex.view_full_profile', 'View Full Profile')}
                  </span>
                </div>

                {isDmLocked ? (
                  <span
                    title={t(
                      'contacts.dm_locked_tooltip',
                      'Direct Messaging is locked. Ask for their number in person or connect via PeerPulse first; Affinity alone does not unlock DMs.'
                    )}
                    className="inline-flex items-center gap-1 py-0.5 px-2 rounded text-[10px] font-semibold bg-neutral-900/80 border border-neutral-700/60 text-gray-400"
                  >
                    <Lock size={10} />
                    <span>{t('contacts.dm_locked_badge', 'DM Locked')}</span>
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 py-0.5 px-2 rounded text-[10px] font-semibold bg-cyan-950/50 border border-cyan-700/50 text-cyan-200">
                    <MessageCircle size={10} />
                    <span>{t('contacts.message_btn', 'Message')}</span>
                  </span>
                )}
              </div>
            </div>

            {isExpanded && (
              <div className="space-y-3 pt-2.5 border-t border-fantasy-border/40 text-xs text-gray-300">
                <div className="p-2 rounded bg-fantasy-accent/10 border border-fantasy-accent/30 text-[11px] text-amber-100/90 leading-snug flex items-start gap-1.5">
                  <Sparkles size={12} className="text-fantasy-accent shrink-0 mt-0.5" />
                  <span>
                    {t(
                      'contacts.promotion_hint',
                      'Promote to Saved Contacts by reaching +15 Affinity, -10 Rivalry, exchanging numbers in person, forming a quest link, or recruiting them into your party.'
                    )}
                  </span>
                </div>

                {isDmLocked && (
                  <div className="p-2 rounded bg-neutral-900/70 border border-neutral-700/60 text-[11px] text-gray-400 leading-snug flex items-start gap-1.5">
                    <Lock size={12} className="text-gray-400 shrink-0 mt-0.5" />
                    <span>
                      {t(
                        'contacts.dm_locked_tooltip',
                        'Direct Messaging is locked. Ask for their number in person or connect via PeerPulse first; Affinity alone does not unlock DMs.'
                      )}
                    </span>
                  </div>
                )}

                {desc && (
                  <div className="bg-black/40 p-2.5 rounded-lg border border-fantasy-border/40 text-xs text-gray-300 leading-relaxed">
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                      {t('contacts.background_notes', '📖 Background & Notes')}
                    </span>
                    {desc}
                  </div>
                )}

                <KnownWardrobeCard npc={acq} t={t} />

                <KnownRoutineCard npc={acq} t={t} />

                {traits.length > 0 && (
                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                      {t('contacts.known_traits', 'Known Traits')}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {traits.map((tr, idx) => {
                        const text = formatItemText(tr);
                        const isMasked = !text || text === maskedSlot || text.includes('???');
                        return (
                          <span
                            key={idx}
                            className={`text-xs px-2 py-0.5 rounded border ${
                              isMasked
                                ? 'bg-black/40 text-gray-500 border-dashed border-neutral-700 font-mono'
                                : 'bg-black/60 text-gray-300 border-fantasy-border'
                            }`}
                          >
                            {text || maskedSlot}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}

                {likes.length > 0 && (
                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                      {t('contacts.preferred_likes', 'Preferred / Likes')}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {likes.map((lk, idx) => {
                        const text = formatItemText(lk);
                        const isMasked = !text || text === maskedSlot || text.includes('???');
                        return (
                          <span
                            key={idx}
                            className={`text-xs px-2 py-0.5 rounded border ${
                              isMasked
                                ? 'bg-black/40 text-gray-500 border-dashed border-neutral-700 font-mono'
                                : 'bg-emerald-950/35 text-emerald-200 border-emerald-800/50'
                            }`}
                          >
                            {text || maskedSlot}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}

                {dislikes.length > 0 && (
                  <div>
                    <span className="text-xs font-bold text-gray-400 uppercase tracking-wider block mb-1">
                      {t('contacts.aversions_dislikes', 'Aversions / Dislikes')}
                    </span>
                    <div className="flex flex-wrap gap-1.5">
                      {dislikes.map((dl, idx) => {
                        const text = formatItemText(dl);
                        const isMasked = !text || text === maskedSlot || text.includes('???');
                        return (
                          <span
                            key={idx}
                            className={`text-xs px-2 py-0.5 rounded border ${
                              isMasked
                                ? 'bg-black/40 text-gray-500 border-dashed border-neutral-700 font-mono'
                                : 'bg-rose-950/35 text-rose-200 border-rose-800/50'
                            }`}
                          >
                            {text || maskedSlot}
                          </span>
                        );
                      })}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
};

export default AcquaintancesView;
