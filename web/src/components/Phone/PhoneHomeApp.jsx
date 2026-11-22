import { MessageSquare, ShieldAlert, Sparkles } from 'lucide-react';

const PhoneHomeApp = ({
  displayTime,
  session,
  appointments = [],
  availableBounties = [],
  apps = [],
  onSelectApp,
  t,
}) => {
  return (
    <div className="flex flex-col h-full space-y-4 select-none pb-2">
      {/* Lockscreen / Clock Widget */}
      <div className="pt-2 pb-1 flex flex-col items-center">
        <span className="font-sans font-light text-5xl text-white tracking-tight drop-shadow-md tabular-nums">
          {displayTime}
        </span>
        <span className="text-xs text-neutral-400 font-medium mt-1 flex items-center gap-1.5">
          <Sparkles size={12} className="text-pink-400" />
          <span>{session?.scenario_display_name || session?.scenario || 'Connected OS'}</span>
          {(session?.current_day ?? session?.day) && (
            <span className="font-mono tabular-nums text-neutral-500">• Day {session?.current_day ?? session?.day}</span>
          )}
          {session?.time_of_day && <span className="text-amber-400/80">• {session.time_of_day}</span>}
        </span>
      </div>

      {/* Quick Glance Notification Banner */}
      {(appointments.length > 0 || availableBounties.length > 0) && (
        <div className="bg-neutral-900/80 border border-neutral-800 rounded-2xl p-2.5 flex items-center justify-between shadow-lg">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-7 h-7 rounded-full bg-pink-500/20 text-pink-300 flex items-center justify-center shrink-0">
              {appointments.length > 0 ? <MessageSquare size={13} /> : <ShieldAlert size={13} />}
            </div>
            <div className="min-w-0">
              <p className="text-[11px] font-bold text-gray-200 truncate">
                {appointments.length > 0
                  ? t('phone.home.rendezvous_planned', '{{count}} Rendezvous Planned', { count: appointments.length })
                  : t('phone.home.requests_posted', '{{count}} Requests Posted', { count: availableBounties.length })}
              </p>
              <p className="text-[10px] text-gray-400 truncate">
                {appointments.length > 0
                  ? t('phone.home.check_messages', 'Check Messages for meetup details')
                  : t('phone.home.visit_requests', 'Visit Campus Requests for active tasks')}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onSelectApp(appointments.length > 0 ? 'dms' : 'bounties')}
            className="px-2.5 py-1 rounded-full bg-pink-600/30 hover:bg-pink-600/50 text-pink-300 text-[10px] font-bold shrink-0 transition-colors border border-pink-500/40"
          >
            {t('phone.home.open', 'Open')}
          </button>
        </div>
      )}

      {/* Main App Grid (iOS / Android Style) */}
      <div className="space-y-2 flex-1 pt-2">
        <div className="flex items-center justify-between px-1">
          <span className="text-[10px] uppercase font-bold tracking-wider text-neutral-500 font-mono">
            {t('phone.home.applications', 'Applications')}
          </span>
          <span className="text-[10px] font-mono tabular-nums text-neutral-600">
            {t('phone.home.installed_count', '{{count}} Installed', { count: apps.length })}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-y-5 gap-x-3 p-1">
          {apps.map((app) => {
            const Icon = app.icon;
            return (
              <button
                key={app.id}
                type="button"
                onClick={() => onSelectApp(app.id)}
                className="flex flex-col items-center group cursor-pointer focus:outline-none transition-transform duration-150 active:scale-95"
              >
                <div
                  className={`w-[3.75rem] h-[3.75rem] rounded-2xl bg-gradient-to-br ${app.gradient} flex items-center justify-center text-white shadow-lg shadow-black/50 group-hover:shadow-pink-500/20 group-hover:scale-105 transition-all relative border border-white/20`}
                >
                  <Icon size={27} className="drop-shadow-md text-white" />
                  {app.badge !== null && app.badge > 0 && (
                    <span
                      className={`absolute -top-1.5 -right-1.5 min-w-5 h-5 px-1 rounded-full ${app.badgeColor} text-white text-[10px] font-bold tabular-nums flex items-center justify-center border-2 border-neutral-950 shadow-md`}
                    >
                      {app.badge}
                    </span>
                  )}
                </div>
                <span className="text-xs font-semibold text-gray-200 mt-1.5 text-center truncate max-w-[88px] group-hover:text-pink-300 transition-colors">
                  {app.name}
                </span>
                <span className="text-[9px] text-gray-500 text-center truncate max-w-[88px]">
                  {app.subtitle}
                </span>
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
};

export default PhoneHomeApp;
