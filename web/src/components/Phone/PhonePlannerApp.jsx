import { Calendar, MapPin } from 'lucide-react';
import { formatCleanLocation } from '../../utils/locationFormat';
import { formatClockTime, getDayOfWeekLabel } from '../../utils/timeFormat';

const PhonePlannerApp = ({
  branding,
  session,
  plannerItems = [],
  cancellingCommitmentId,
  onCancelPlannerItem,
  onOpenMessages,
  onOpenChatWithContact,
  commsOffline = false,
  clockFormat = '12h',
  t,
}) => {
  return (
    <div className="flex-1 flex flex-col min-h-0 text-neutral-100 overflow-hidden">
      {/* App Subheader */}
      <div className="px-4 py-3 bg-neutral-900/90 border-b border-neutral-800 rounded-t-xl flex items-center justify-between shrink-0">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-blue-500 to-sky-600 flex items-center justify-center text-white shadow-sm">
            <Calendar size={16} />
          </div>
          <div>
            <h3 className="text-xs font-bold text-neutral-200 uppercase tracking-wider">
              {branding.planner_app_name || 'Planner & Agenda'}
            </h3>
            <p className="text-[10px] text-neutral-400 font-mono">
              {getDayOfWeekLabel(session?.current_day || 1, t)} • In-Game Timeline
            </p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="px-2 py-0.5 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 text-[10px] font-mono tabular-nums">
            {plannerItems.length} Active
          </span>
        </div>
      </div>

      {/* Unified Commitments & Rendezvous List */}
      <div className="flex-1 overflow-y-auto p-3.5 space-y-3">
        {plannerItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-52 text-center text-neutral-500 space-y-2">
            <div className="w-12 h-12 rounded-full bg-neutral-900 border border-neutral-800 flex items-center justify-center text-neutral-600">
              <Calendar size={22} />
            </div>
            <div className="text-xs font-medium text-neutral-400">
              {t('phone.home.no_active_meetups', 'No Active Meetups or Promises')}
            </div>
            <p className="text-[10px] max-w-[220px] text-neutral-500 leading-relaxed">
              Message a contact or agree on plans and promises in conversation to track them here.
            </p>
            <button
              type="button"
              onClick={onOpenMessages}
              className="mt-2 px-3 py-1.5 rounded-xl bg-blue-600/20 hover:bg-blue-600/30 text-blue-300 border border-blue-500/30 text-[11px] font-medium transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
            >
              Open Messages
            </button>
          </div>
        ) : (
          plannerItems.map((appt, i) => {
            const cId = appt.commitment_id || appt.id;
            const cType = (
              appt.commitment_type ||
              (appt.rendezvous_location || appt.target_location ? 'rendezvous' : 'promise')
            ).toLowerCase();
            const isRendezvous = cType === 'rendezvous';
            const isArrived = appt.status === 'arrived';
            const isConfidential = Boolean(appt.is_confidential);
            const shortLoc = formatCleanLocation(
              appt.rendezvous_location || appt.target_location || '',
              { includeZone: false }
            );
            const npcName = appt.target_display_name || appt.npc_name || appt.target_entity || 'Contact';
            const subtypeLabel = (appt.subtype || cType).replace(/_/g, ' ');
            const canCancel = Boolean(
              cId && ['active', 'pending', 'arrived'].includes((appt.status || 'pending').toLowerCase())
            );

            const hasOverlapConflict =
              isRendezvous &&
              plannerItems.some((other) => {
                if (!other || (other.commitment_id || other.id) === cId) return false;
                const oType = (
                  other.commitment_type ||
                  (other.rendezvous_location || other.target_location ? 'rendezvous' : 'promise')
                ).toLowerCase();
                if (oType !== 'rendezvous') return false;
                const sameDay = (other.scheduled_day || 1) === (appt.scheduled_day || 1);
                if (!sameDay) return false;
                const oStart = other.start_minute ?? 0;
                const oEnd = other.end_minute ?? 1439;
                const aStart = appt.start_minute ?? 0;
                const aEnd = appt.end_minute ?? 1439;
                return Math.max(oStart, aStart) < Math.min(oEnd, aEnd);
              });

            const startMinVal = appt.start_minute ?? appt.created_minute;
            const endMinVal = appt.end_minute ?? appt.expiry_minute;
            const hasNumericWindow =
              isRendezvous &&
              startMinVal !== undefined &&
              startMinVal !== null &&
              Number.isFinite(Number(startMinVal));
            const timeWindowLabel = hasNumericWindow
              ? `Day ${appt.scheduled_day || 1} • ${formatClockTime(startMinVal, clockFormat)}${
                  endMinVal !== undefined && endMinVal !== null && Number.isFinite(Number(endMinVal))
                    ? `–${formatClockTime(endMinVal, clockFormat)}`
                    : ''
                }`
              : appt.time_window_label ||
                (isRendezvous
                  ? `Day ${appt.scheduled_day || 1}`
                  : appt.scheduled_day
                    ? `Day ${appt.scheduled_day}`
                    : 'Open Obligation');

            return (
              <div
                key={cId || i}
                className={`p-3.5 rounded-2xl border transition-all ${
                  isArrived
                    ? 'bg-emerald-950/20 border-emerald-500/40 shadow-sm shadow-emerald-950/50'
                    : 'bg-neutral-900/60 border-neutral-800/80 hover:border-neutral-700'
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-center gap-2 min-w-0">
                    <div
                      className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold shrink-0 ${
                        isArrived
                          ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                          : 'bg-neutral-800 text-neutral-300'
                      }`}
                    >
                      {npcName.slice(0, 2).toUpperCase()}
                    </div>
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-neutral-100 flex items-center gap-1.5 flex-wrap">
                        <span>{appt.title || npcName}</span>
                        <span className="text-[9px] px-1.5 py-0.5 rounded bg-blue-950/60 text-blue-300 border border-blue-800/40 uppercase font-mono">
                          {subtypeLabel}
                        </span>
                        {isConfidential && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-purple-950/60 text-purple-300 border border-purple-800/40">
                            Private 1-on-1
                          </span>
                        )}
                        {hasOverlapConflict && (
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-amber-950/60 text-amber-300 border border-amber-800/40">
                            ⚠️ Overlap
                          </span>
                        )}
                      </div>
                      <div className="text-[10px] text-neutral-400 flex items-center gap-1 mt-0.5">
                        {shortLoc ? (
                          <>
                            <MapPin size={10} className="text-neutral-500 shrink-0" />
                            <span className="truncate max-w-[180px]">{shortLoc}</span>
                          </>
                        ) : (
                          <span className="truncate max-w-[180px]">👤 {npcName}</span>
                        )}
                      </div>
                    </div>
                  </div>

                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-full font-mono font-medium shrink-0 ${
                      isArrived
                        ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                        : 'bg-amber-500/10 text-amber-400 border border-amber-500/20'
                    }`}
                  >
                    {isArrived ? 'Arrived & Waiting' : isRendezvous ? 'Scheduled' : 'Active'}
                  </span>
                </div>

                {(appt.description || appt.topic) && (
                  <p className="mt-2.5 text-[11px] text-neutral-300 bg-neutral-950/60 p-2 rounded-xl border border-neutral-800/60 italic">
                    "{appt.description || appt.topic}"
                  </p>
                )}

                <div className="mt-3 pt-2.5 border-t border-neutral-800/60 flex items-center justify-between gap-2 text-[10px]">
                  <span className="text-neutral-400 font-mono tabular-nums truncate">
                    {timeWindowLabel}
                  </span>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {canCancel && (
                      <button
                        type="button"
                        disabled={commsOffline || cancellingCommitmentId === cId}
                        onClick={() => onCancelPlannerItem(cId)}
                        className="px-2 py-1 rounded-lg bg-rose-950/50 hover:bg-rose-900/60 text-rose-300 border border-rose-800/50 text-[10px] font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rose-400"
                      >
                        {cancellingCommitmentId === cId ? '...' : 'Cancel'}
                        <span className="sr-only"> {appt.title || npcName}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => onOpenChatWithContact(appt.npc_id || npcName)}
                      className="px-2.5 py-1 rounded-lg bg-neutral-800 hover:bg-neutral-700 text-neutral-200 text-[10px] font-medium transition-colors cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-400"
                    >
                      Message Contact
                      <span className="sr-only"> {npcName}</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};

export default PhonePlannerApp;
