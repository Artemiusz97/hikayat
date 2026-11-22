import { CheckCircle2, Circle, MapPin, ScrollText } from 'lucide-react';
import { cleanProseLocations, formatCleanLocation } from '../../../utils/locationFormat';

const CampaignTab = ({
  currentChapter = 1,
  maxChapters = 11,
  campaignSpine = null,
  campaignEndGoals = [],
  chapterDigest = [],
  busyAction,
  onOpenTapestry,
  onChooseEpilogue,
  t,
}) => {
  return (
    <div className="space-y-3.5">
      {/* Chapter Progress Bar */}
      <div className="pb-2.5 border-b border-fantasy-border/30 space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[11px] font-bold text-fantasy-accent uppercase tracking-wider">
            {t('quests.campaign_arc_progress', 'Campaign Arc Progress')}
          </span>
          <span className="font-mono text-xs font-bold text-gray-100 shrink-0">
            {t('quests.chapter_n', { chapter: currentChapter || 1, defaultValue: `Chapter ${currentChapter || 1}` })} /{' '}
            {maxChapters || 11}
          </span>
        </div>
        <div className="h-2 w-full bg-black/80 rounded-full overflow-hidden border border-fantasy-border/50">
          <div
            className="h-full bg-gradient-to-r from-fantasy-accent to-amber-400 transition-all duration-500"
            style={{ width: `${Math.max(8, Math.min(100, ((currentChapter || 1) / (maxChapters || 11)) * 100))}%` }}
          />
        </div>
      </div>

      {/* Playable Fallen-World Chapter 11 Active Banner */}
      {campaignSpine?.fallen_world && !campaignSpine?.epilogue_ready && !campaignSpine?.campaign_archived && (
        <div className="bg-rose-950/50 border border-rose-600/60 rounded-xl p-3 space-y-1 text-xs text-rose-100">
          <strong className="uppercase tracking-wider text-rose-300 block">
            🌑 {t('quests.fallen_world_ch11_active', 'Fallen World — Chapter 11 Underground Resistance')}
          </strong>
          <p className="text-[12px] leading-snug text-rose-200/90 hk-quest-prose">
            {t(
              'quests.fallen_world_ch11_desc',
              'Chapter 10 ended in defeat, plunging the realm into shadow. Protect your inner circle and forge the resistance in this playable epilogue!'
            )}
          </p>
        </div>
      )}

      {/* 4-Slide Chronicle Tapestry Access Card */}
      {Array.isArray(campaignSpine?.chronicle_tapestry?.slides) &&
        campaignSpine.chronicle_tapestry.slides.length > 0 && (
          <div className="bg-gradient-to-br from-fantasy-dark via-black/60 to-amber-950/25 border border-fantasy-accent/60 rounded-xl p-3 space-y-2">
            <div className="flex items-center justify-between gap-2 flex-wrap">
              <span className="text-[11px] font-bold uppercase tracking-wider text-fantasy-accent flex items-center gap-1.5">
                <ScrollText size={13} />
                <span>{t('quests.chronicle_tapestry', 'Chronicle Tapestry')}</span>
              </span>
              {campaignSpine.chronicle_tapestry.earned_title && (
                <span className="text-[10.5px] font-mono px-1.5 py-0.5 rounded bg-black/60 text-amber-300 border border-amber-700/50">
                  🏅 {cleanProseLocations(campaignSpine.chronicle_tapestry.earned_title)}
                </span>
              )}
            </div>
            <p className="text-[13px] font-semibold text-gray-100 leading-snug">
              {cleanProseLocations(campaignSpine.chronicle_tapestry.ending_title)}
            </p>
            <button
              type="button"
              onClick={onOpenTapestry}
              className="w-full py-1.5 px-3 rounded-lg bg-fantasy-accent/20 hover:bg-fantasy-accent/35 text-fantasy-accent border border-fantasy-accent/50 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
            >
              <ScrollText size={13} />
              <span>{t('quests.view_chronicle_tapestry', 'View 4-Slide Chronicle Tapestry')}</span>
            </button>
          </div>
        )}

      {/* Ch.10 Hard Game Over */}
      {campaignSpine?.campaign_game_over && (
        <div className="bg-red-950/55 border border-red-600/60 rounded-xl p-3 space-y-1 text-xs text-red-200">
          <strong className="uppercase tracking-wider text-red-300 block">
            💀 {t('quests.fallen_world', 'Fallen World — Chapter 10 Climax Defeat')}
          </strong>
          <p className="text-[12px] leading-snug hk-quest-prose">
            {t(
              'quests.fallen_world_ch10_desc',
              'The campaign mastermind triumphed in the Chapter 10 finale. Load a prior checkpoint or begin a new legend.'
            )}
          </p>
        </div>
      )}

      {/* Ch.11 Universal Epilogue Decision Banner */}
      {campaignSpine?.epilogue_ready && (
        <div className="bg-amber-950/40 border border-amber-500/60 rounded-xl p-3 space-y-2 text-xs text-amber-100">
          <strong className="uppercase tracking-wider text-amber-300 block">
            🌅 {t('quests.epilogue_ready', 'Chapter 11 Playable Epilogue Ready')}
          </strong>
          <div className="flex items-center gap-2 pt-1">
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => onChooseEpilogue('archive')}
              className="flex-1 py-1.5 px-2.5 rounded-lg bg-fantasy-accent/25 hover:bg-fantasy-accent/40 text-amber-200 border border-fantasy-accent/60 text-[11px] font-bold transition-colors"
            >
              🏛️ {t('quests.epilogue_archive', 'Archive Campaign')}
            </button>
            <button
              type="button"
              disabled={Boolean(busyAction)}
              onClick={() => onChooseEpilogue('endless')}
              className="flex-1 py-1.5 px-2.5 rounded-lg bg-emerald-950/60 hover:bg-emerald-900/70 text-emerald-200 border border-emerald-600/60 text-[11px] font-bold transition-colors"
            >
              ♾️ {t('quests.epilogue_endless', 'Continue in Endless World')}
            </button>
          </div>
        </div>
      )}

      {/* Active World Scars */}
      {Array.isArray(campaignSpine?.world_scars) && campaignSpine.world_scars.length > 0 && (
        <div className="pt-2 border-t border-white/[0.08] space-y-2">
          <span className="text-[10.5px] font-bold text-rose-300 uppercase tracking-wider block">
            🔥 {t('quests.world_scars', 'Active World Scars')} ({campaignSpine.world_scars.length})
          </span>
          <div className="space-y-2">
            {campaignSpine.world_scars.map((sc, sIdx) => (
              <div
                key={sc.event_key || sIdx}
                className="border-l-2 border-rose-500 bg-rose-950/20 rounded-r-lg px-2.5 py-2 space-y-1"
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="font-bold text-[12.5px] text-rose-200">{sc.title}</span>
                  {sc.scar_tier === 'peak' && (
                    <span className="text-[9.5px] font-mono uppercase px-1.5 py-0.5 rounded bg-rose-950/80 text-rose-300 border border-rose-600/60">
                      ⚡ {t('quests.peak_scar', 'Peak Scar')}
                    </span>
                  )}
                  {sc.scar_tier === 'buildup' && (
                    <span className="text-[9.5px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-950/70 text-amber-300 border border-amber-700/50">
                      ⚔️ {t('quests.liberation_op', 'Liberation Op')}
                    </span>
                  )}
                </div>
                {sc.location_name && (
                  <div className="flex items-start gap-1 text-[11px] text-amber-300">
                    <MapPin size={11} className="shrink-0 mt-0.5" />
                    <span className="break-words">{formatCleanLocation(sc.location_name)}</span>
                  </div>
                )}
                {sc.description && (
                  <p className="text-[12px] text-gray-300 leading-snug hk-quest-prose">{sc.description}</p>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Campaign End Goals */}
      <div className="pt-2 border-t border-white/[0.08] space-y-2">
        <span className="text-[10.5px] font-bold text-amber-300 uppercase tracking-wider block">
          🏆 {t('quests.campaign_end_goals', 'Campaign End Goals')}
        </span>
        {campaignEndGoals.length === 0 ? (
          <p className="text-xs text-gray-400 italic leading-relaxed">
            {t('quests.milestones_empty', 'Long-term victory milestones will crystallize as your adventure unfolds.')}
          </p>
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {campaignEndGoals.map((goal, idx) => {
              const isDone = typeof goal === 'object' && Boolean(goal.completed || goal.done);
              const text = typeof goal === 'string' ? goal : goal.text || goal.title || goal.goal || goal.description;
              return (
                <div key={idx} className="flex items-start gap-2 py-2 first:pt-0 last:pb-0 text-[12.5px] leading-snug">
                  {isDone ? (
                    <CheckCircle2 size={14} className="text-emerald-400 shrink-0 mt-0.5" />
                  ) : (
                    <Circle size={14} className="text-fantasy-accent shrink-0 mt-0.5" />
                  )}
                  <span className={isDone ? 'text-gray-500 line-through hk-quest-prose' : 'text-gray-200 hk-quest-prose'}>
                    {cleanProseLocations(text)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Rolling Chapter Digest */}
      <div className="pt-2 border-t border-white/[0.08] space-y-2">
        <span className="text-[10.5px] font-bold text-purple-300 uppercase tracking-wider block">
          📜 {t('quests.chronicle_digest', 'Chronicle Digest (Story So Far)')}
        </span>
        {chapterDigest.length === 0 ? (
          <p className="text-xs text-gray-400 italic leading-relaxed">
            {t('quests.chronicles_empty', 'Completed chapters and major turning points will be summarized here.')}
          </p>
        ) : (
          <div className="divide-y divide-white/[0.06]">
            {chapterDigest.map((entry, idx) => (
              <div key={idx} className="py-2 first:pt-0 last:pb-0 text-[12px] text-gray-200 leading-relaxed hk-quest-prose">
                • {typeof entry === 'string' ? entry : entry.summary || entry.text || entry.event}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default CampaignTab;
