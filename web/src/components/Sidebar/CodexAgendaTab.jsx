import { Calendar, Clock, MapPin, Scroll } from 'lucide-react';
import { cleanProseLocations, formatCleanLocation } from '../../utils/locationFormat';
import { formatClockTime } from '../../utils/timeFormat';

const CodexAgendaTab = ({
  filteredCommitments,
  clockFormat,
  cancellingCommitmentId,
  onCancelAgendaItem,
  findDiscoveredContact,
  onJumpToContact,
  t,
}) => (
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

        const hasStartMin = c.start_minute !== undefined && c.start_minute !== null;
        const hasEndMin = c.end_minute !== undefined && c.end_minute !== null;
        const formattedSpan = hasStartMin
          ? hasEndMin
            ? `${formatClockTime(c.start_minute, clockFormat)}–${formatClockTime(c.end_minute, clockFormat)}`
            : formatClockTime(c.start_minute, clockFormat)
          : '';
        const timeWindowLabel =
          isRendezvous && c.scheduled_day && formattedSpan
            ? `Day ${c.scheduled_day} • ${formattedSpan}`
            : c.time_window_label || (c.scheduled_day ? `Day ${c.scheduled_day}` : 'Open Obligation');

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
                <span className="text-[9px] px-1.5 py-0.5 rounded bg-fantasy-dark text-gray-300 border border-fantasy-border/60 uppercase font-mono">
                  {subtypeLabel}
                </span>
                {hasOverlapConflict && (
                  <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                    ⚠️ Overlap
                  </span>
                )}
              </div>

              <span className={`text-[9px] px-1.5 py-0.5 rounded font-mono uppercase font-bold border shrink-0 ${
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
                      onClick={() => onJumpToContact(matchedTarget)}
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
                  <span className="text-[9px] px-1 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
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
                    onClick={() => onCancelAgendaItem(cId, cardTitle)}
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
);

export default CodexAgendaTab;
