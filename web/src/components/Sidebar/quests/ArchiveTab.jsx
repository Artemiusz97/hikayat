import { Archive } from 'lucide-react';
import { cleanProseLocations } from '../../../utils/locationFormat';

const ArchiveTab = ({
  archivedQuests = [],
  chapterDigest = [],
  historyFilter,
  onChangeFilter,
  t,
}) => {
  const filteredArchivedQuests = archivedQuests.filter(
    (q) => historyFilter === 'all' || q.status === historyFilter
  );

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-2 flex-wrap border-b border-white/[0.08] pb-2">
        <h4 className="font-bold text-xs text-fantasy-accent uppercase tracking-wider flex items-center gap-1.5">
          <Archive size={14} />
          <span>
            {t('quests.history_tab', 'Archive')} ({archivedQuests.length})
          </span>
        </h4>
        <div className="flex items-center gap-1 flex-wrap">
          {[
            { id: 'all', label: t('quests.filter_all', 'All') },
            { id: 'Completed', label: t('quests.completed', 'Completed') },
            { id: 'Failed', label: t('quests.failed', 'Failed') },
            { id: 'Abandoned', label: t('quests.abandoned', 'Abandoned') },
          ].map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => onChangeFilter(f.id)}
              className={`px-2 py-0.5 rounded text-[10.5px] font-semibold border transition-colors ${
                historyFilter === f.id
                  ? 'bg-fantasy-accent/20 text-fantasy-accent border-fantasy-accent/50'
                  : 'bg-black/40 text-gray-400 border-fantasy-border/50 hover:text-gray-200'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {filteredArchivedQuests.length > 0 && (
        <div className="divide-y divide-fantasy-border/30">
          {filteredArchivedQuests.map((aq, idx) => {
            const st = aq.status || 'Completed';
            const badgeStyle =
              st === 'Completed'
                ? 'text-emerald-300 bg-emerald-950/60 border-emerald-700/50'
                : st === 'Failed'
                  ? 'text-red-300 bg-red-950/60 border-red-700/50'
                  : 'text-gray-300 bg-neutral-900 border-neutral-700/60';
            return (
              <div key={aq.quest_id || idx} className="py-2.5 space-y-1">
                <div className="flex items-start justify-between gap-2">
                  <span className="text-[12.5px] font-semibold text-gray-100 leading-snug hk-quest-prose">
                    {cleanProseLocations(aq.title)}
                  </span>
                  <span className={`text-[9.5px] px-1.5 py-0.5 rounded border uppercase font-mono shrink-0 ${badgeStyle}`}>
                    {st}
                  </span>
                </div>
                {aq.objective && (
                  <p className="text-[11.5px] text-gray-400 leading-snug hk-quest-prose">
                    {cleanProseLocations(aq.objective)}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}

      {chapterDigest.length > 0 && (
        <div className="space-y-2 pt-2 border-t border-white/[0.08]">
          <span className="text-[10.5px] font-bold uppercase tracking-wider text-gray-400 block">
            Chapter Digest
          </span>
          <div className="divide-y divide-white/[0.06] bg-black/25 border border-fantasy-border/45 rounded-xl px-3">
            {chapterDigest.map((digest, idx) => {
              const isStr = typeof digest === 'string';
              const turnMatch = isStr ? digest.match(/\[?Turn\s*(\d+)\]?/i) : null;
              const turnNum = !isStr && digest?.turn ? digest.turn : turnMatch ? turnMatch[1] : null;
              const digestText = isStr
                ? digest.replace(/^\[?Turn\s*\d+\]?:?\s*/i, '').trim() || digest
                : digest?.summary || digest?.narrative || '';
              return (
                <div key={idx} className="py-2.5 space-y-1">
                  <span className="text-[10.5px] font-mono text-gray-400 block">
                    {turnNum ? `Turn ${turnNum}` : `${t('quests.chapter_note', 'Chapter Note')} #${idx + 1}`}
                  </span>
                  <p className="text-[12px] text-gray-200 leading-snug hk-quest-prose">{digestText}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {filteredArchivedQuests.length === 0 && chapterDigest.length === 0 && (
        <p className="text-xs text-gray-400 italic text-center py-6 border border-dashed border-neutral-800 rounded-xl">
          No history recorded yet.
        </p>
      )}
    </div>
  );
};

export default ArchiveTab;
