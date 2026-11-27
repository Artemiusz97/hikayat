import { Camera, MessageSquare, ShieldAlert, Sparkles } from 'lucide-react';

const DOCK_APP_IDS = ['dms', 'photos', 'feed', 'settings'];

const PhoneHomeApp = ({
  displayTime,
  session,
  appointments = [],
  availableBounties = [],
  mediaGallery = [],
  apps = [],
  onSelectApp,
  clockStyle = 'modern',
  uiStyle = 'classic',
  t,
}) => {
  const isGlass = uiStyle === 'glass';
  const dockApps = DOCK_APP_IDS.map((id) => apps.find((a) => a.id === id)).filter(Boolean);
  const gridApps = apps.filter((a) => !DOCK_APP_IDS.includes(a.id));

  // Build up to 2 compact notification cards so rendezvous, bounties, and new media don't hide each other
  const notifications = [];
  if (appointments.length > 0) {
    notifications.push({
      id: 'rendezvous',
      appId: 'dms',
      icon: MessageSquare,
      iconBg: 'bg-pink-500/25 text-pink-300',
      btnCls: 'bg-pink-600/35 hover:bg-pink-600/55 text-pink-100 border-pink-400/40',
      title: t('phone.home.rendezvous_planned', '{{count}} Rendezvous Planned', {
        count: appointments.length,
      }),
      sub: t('phone.home.check_messages', 'Check Messages for meetup details'),
    });
  }
  if (availableBounties.length > 0) {
    const bountyAppId = apps.some((a) => a.id === 'bounties')
      ? 'bounties'
      : apps.some((a) => a.id === 'school_bounties')
      ? 'school_bounties'
      : 'bounties';
    notifications.push({
      id: 'bounties',
      appId: bountyAppId,
      icon: ShieldAlert,
      iconBg: 'bg-rose-500/25 text-rose-300',
      btnCls: 'bg-rose-600/35 hover:bg-rose-600/55 text-rose-100 border-rose-400/40',
      title: t('phone.home.requests_posted', '{{count}} Requests Posted', {
        count: availableBounties.length,
      }),
      sub:
        bountyAppId === 'school_bounties'
          ? t('phone.home.visit_requests', 'Visit Campus Requests for active tasks')
          : t('phone.home.visit_bounty_board', 'Visit Bounty Board for active contracts'),
    });
  }
  if (notifications.length < 2 && mediaGallery.length > 0) {
    const latestMedia = mediaGallery[mediaGallery.length - 1];
    notifications.push({
      id: 'vault',
      appId: 'photos',
      icon: Camera,
      iconBg: 'bg-purple-500/25 text-purple-300',
      btnCls: 'bg-purple-600/35 hover:bg-purple-600/55 text-purple-100 border-purple-400/40',
      title: t('phone.home.vault_memories', '{{count}} Saved in Photo Vault', {
        count: mediaGallery.length,
      }),
      sub: latestMedia?.contact_name
        ? t('phone.home.latest_from', 'Latest from {{name}}', { name: latestMedia.contact_name })
        : t('phone.home.tap_to_view_photos', 'Tap to view photos & wallpapers'),
    });
  }
  const visibleNotifications = notifications.slice(0, 2);

  return (
    <div className="flex flex-col h-full min-h-0 select-none gap-3">
      {/* Lockscreen / Clock Widget */}
      <div className="pt-2 pb-1 flex flex-col items-center shrink-0">
        <span
          className={`text-5xl leading-none hk-phone-home-text tabular-nums ${
            clockStyle === 'serif'
              ? 'font-rpg font-semibold tracking-wide'
              : 'font-sans font-light tracking-tight'
          }`}
        >
          {displayTime}
        </span>
        <span className="text-xs font-medium mt-1.5 flex items-center justify-center flex-wrap gap-1.5 hk-phone-home-subtext text-center px-2">
          <Sparkles size={12} className="text-pink-400 shrink-0" />
          <span className="truncate max-w-[200px]">
            {session?.scenario_display_name || session?.scenario || 'Connected OS'}
          </span>
          {(session?.current_day ?? session?.day) && (
            <span className="font-mono tabular-nums">
              • Day {session?.current_day ?? session?.day}
            </span>
          )}
          {session?.time_of_day && (
            <span className="hk-phone-home-accent font-semibold">• {session.time_of_day}</span>
          )}
        </span>
      </div>

      {/* Compact Notification Stack (max 2 cards) */}
      {visibleNotifications.length > 0 && (
        <div className="space-y-1.5 shrink-0">
          {visibleNotifications.map((notif) => {
            const NIcon = notif.icon;
            return (
              <div
                key={notif.id}
                className={`rounded-2xl px-2.5 py-2 flex items-center justify-between gap-2 shadow-lg border ${
                  isGlass
                    ? 'hk-phone-chrome'
                    : 'hk-phone-notif-classic backdrop-blur-md border'
                }`}
              >
                <div className="flex items-center gap-2 min-w-0">
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center shrink-0 ${notif.iconBg}`}
                  >
                    <NIcon size={13} />
                  </div>
                  <div className="min-w-0">
                    <p
                      className={`text-[11px] font-bold truncate ${
                        isGlass ? 'text-gray-100' : 'hk-phone-home-text'
                      }`}
                    >
                      {notif.title}
                    </p>
                    <p
                      className={`text-[10px] truncate ${
                        isGlass ? 'text-gray-400' : 'hk-phone-home-subtext'
                      }`}
                    >
                      {notif.sub}
                    </p>
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => onSelectApp(notif.appId)}
                  className={`px-2.5 py-1 rounded-full text-[10px] font-bold shrink-0 transition-colors border cursor-pointer ${notif.btnCls}`}
                >
                  {t('phone.home.open', 'Open')}
                </button>
              </div>
            );
          })}
        </div>
      )}

      {/* Upper App Grid (leaves breathing room in middle for wallpaper) */}
      <div className="space-y-2 pt-1 shrink-0">
        <div className="flex items-center justify-between px-1">
          <span className="text-[10px] uppercase font-bold tracking-wider font-mono hk-phone-home-subtext">
            {t('phone.home.applications', 'Applications')}
          </span>
          <span className="text-[10px] font-mono tabular-nums hk-phone-home-subtext">
            {t('phone.home.installed_count', '{{count}} Installed', { count: apps.length })}
          </span>
        </div>

        <div className="grid grid-cols-3 gap-y-4 gap-x-2 p-1">
          {gridApps.map((app) => {
            const Icon = app.icon;
            return (
              <button
                key={app.id}
                type="button"
                onClick={() => onSelectApp(app.id)}
                className="flex flex-col items-center group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/80 rounded-2xl transition-transform duration-150 active:scale-95"
              >
                <div
                  className={`w-14 h-14 rounded-2xl bg-gradient-to-br ${app.gradient} flex items-center justify-center shadow-lg shadow-black/50 group-hover:shadow-pink-500/25 group-hover:scale-105 transition-all relative border border-white/25`}
                >
                  <Icon size={25} className="drop-shadow-md hk-phone-icon-glyph" />
                  {app.badge !== null && app.badge > 0 && (
                    <span
                      className={`absolute -top-1.5 -right-1.5 min-w-5 h-5 px-1 rounded-full ${app.badgeColor} hk-phone-icon-glyph text-[10px] font-bold tabular-nums flex items-center justify-center border-2 border-white/80 shadow-md`}
                    >
                      {app.badge}
                    </span>
                  )}
                </div>
                <span className="text-[11px] font-semibold hk-phone-home-text mt-1.5 text-center leading-tight line-clamp-2 max-w-[96px] transition-colors">
                  {app.name}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Spacer allowing wallpaper focal showcase */}
      <div className="flex-1 min-h-[16px]" />

      {/* Pinned Bottom Dock (4 Core Apps) */}
      {dockApps.length > 0 && (
        <div className="pt-1 pb-1 shrink-0">
          <div className="rounded-3xl p-2.5 hk-phone-dock hk-phone-dock-classic grid grid-cols-4 gap-2">
            {dockApps.map((app) => {
              const Icon = app.icon;
              return (
                <button
                  key={app.id}
                  type="button"
                  onClick={() => onSelectApp(app.id)}
                  title={app.name}
                  aria-label={app.name}
                  className="flex flex-col items-center group cursor-pointer focus:outline-none focus-visible:ring-2 focus-visible:ring-sky-400/80 rounded-2xl transition-transform duration-150 active:scale-95"
                >
                  <div
                    className={`w-12 h-12 rounded-2xl bg-gradient-to-br ${app.gradient} flex items-center justify-center shadow-md shadow-black/45 group-hover:scale-105 transition-all relative border border-white/25`}
                  >
                    <Icon size={22} className="drop-shadow-md hk-phone-icon-glyph" />
                    {app.badge !== null && app.badge > 0 && (
                      <span
                        className={`absolute -top-1.5 -right-1.5 min-w-4 h-4 px-1 rounded-full ${app.badgeColor} hk-phone-icon-glyph text-[9px] font-bold tabular-nums flex items-center justify-center border border-white/80 shadow`}
                      >
                        {app.badge}
                      </span>
                    )}
                  </div>
                  <span
                    className={`text-[9.5px] font-semibold mt-1 text-center truncate max-w-[68px] ${
                      isGlass ? 'text-gray-100' : 'hk-phone-home-text'
                    }`}
                  >
                    {app.shortName || app.name}
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
};

export default PhoneHomeApp;
