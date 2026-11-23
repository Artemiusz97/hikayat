import { Camera, Image as ImageIcon, Loader2, Play, Video } from 'lucide-react';
import { formatTimestamp } from './phoneHelpers';
import { isIntimateMediaItem, isVideoMediaItem } from './phoneWallpapers';

const PhonePhotosApp = ({
  branding,
  mediaGallery = [],
  filteredGallery = [],
  galleryContacts = [],
  photoCategory,
  onChangePhotoCategory,
  photoContactFilter,
  onChangePhotoContactFilter,
  onSelectPhoto,
  clockFormat = '12h',
  t,
}) => {
  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between pb-1 border-b border-neutral-800/80">
        <h4 className="font-bold text-sm text-gray-100 flex items-center gap-1.5">
          <Camera size={15} className="text-pink-400" />
          <span>{branding.gallery_app_name || 'Photo Vault'}</span>
        </h4>
        <span className="text-[11px] font-mono tabular-nums text-gray-400 font-medium">
          {filteredGallery.length} / {mediaGallery.length} Items
        </span>
      </div>

      {/* Category Filter Pills & Contact Dropdown */}
      <div className="space-y-1.5">
        <div className="grid grid-cols-4 gap-1.5 pb-0.5">
          {[
            { id: 'all', label: t('phone.vault.all', 'All') },
            { id: 'photo', label: t('phone.vault.photos', '📸 Photos') },
            { id: 'intimate', label: t('phone.vault.intimate', '🔥 Intimate') },
            { id: 'video', label: t('phone.vault.videos', '🎥 Videos') },
          ].map((cat) => (
            <button
              key={cat.id}
              type="button"
              onClick={() => onChangePhotoCategory(cat.id)}
              className={`py-1.5 rounded-xl text-[11px] font-bold transition-colors text-center border cursor-pointer ${
                photoCategory === cat.id
                  ? 'bg-pink-600/30 text-pink-300 border-pink-500/50 shadow-xs'
                  : 'bg-neutral-900 text-gray-400 border-neutral-800 hover:text-gray-200'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {galleryContacts.length > 0 && (
          <select
            value={photoContactFilter}
            onChange={(e) => onChangePhotoContactFilter(e.target.value)}
            className="w-full bg-neutral-900 border border-neutral-800 rounded-xl px-2.5 py-1 text-[11px] text-gray-200 focus:outline-none focus:border-pink-500"
          >
            <option value="__all__">
              {t('phone.vault.all_contacts', '👤 All Contacts ({{count}})', {
                count: mediaGallery.length,
              })}
            </option>
            {galleryContacts.map((cName) => (
              <option key={cName} value={cName}>
                👤 {cName}
              </option>
            ))}
          </select>
        )}
      </div>

      {filteredGallery.length === 0 ? (
        <div className="text-center py-14 px-4 text-gray-500 border border-dashed border-neutral-800 rounded-2xl space-y-2">
          <ImageIcon size={32} className="mx-auto opacity-30 text-pink-400" />
          <p className="text-xs font-medium text-gray-400">
            {t('phone.vault.empty', 'No matching media in vault.')}
          </p>
          <p className="text-[11px] text-gray-500 leading-relaxed">
            Capture photos, selfies, and videos through narrative choices or DMs to collect digital memories!
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2.5">
          {filteredGallery.map((media) => {
            const isVideo = isVideoMediaItem(media);
            const isIntimate = isIntimateMediaItem(media);
            const hasImage = Boolean(media.image_url);
            const isGenerating = media.image_status === 'generating';

            return (
              <div
                key={media.id || media.name}
                onClick={() => onSelectPhoto(media)}
                className="bg-neutral-900/80 border border-neutral-800 hover:border-pink-500/50 rounded-xl p-2 space-y-1.5 cursor-pointer transition-all hover:scale-[1.02] shadow-sm relative group overflow-hidden"
              >
                <div className="h-32 rounded-lg bg-neutral-950 border border-neutral-800/80 flex flex-col items-center justify-center relative overflow-hidden text-center">
                  {hasImage ? (
                    <>
                      <img
                        src={media.image_url}
                        alt={media.caption || media.name}
                        loading="lazy"
                        className="absolute inset-0 w-full h-full object-cover object-top"
                      />
                      <div className="absolute inset-x-0 bottom-0 h-10 hk-phone-thumb-scrim pointer-events-none" />
                      <span className="relative z-10 mt-auto pb-1.5 px-1.5 text-[10px] font-semibold hk-phone-home-text truncate max-w-full">
                        {media.contact_name}
                      </span>
                      {isVideo && (
                        <span className="absolute inset-0 m-auto w-8 h-8 rounded-full hk-phone-play-badge flex items-center justify-center hk-phone-icon-glyph pointer-events-none">
                          <Play size={14} className="ml-0.5" />
                        </span>
                      )}
                    </>
                  ) : isGenerating ? (
                    <div className="flex flex-col items-center justify-center gap-1.5 p-2 animate-pulse">
                      <Loader2 size={18} className="animate-spin text-pink-400" />
                      <span className="text-[10px] font-semibold text-pink-300">
                        {t('phone.vault.generating', 'Developing...')}
                      </span>
                    </div>
                  ) : (
                    <div className="flex flex-col items-center justify-center p-1.5">
                      <div
                        className={`w-8 h-8 rounded-full flex items-center justify-center mb-1 ${
                          isIntimate
                            ? 'bg-pink-950/60 text-pink-400'
                            : isVideo
                              ? 'bg-cyan-950/60 text-cyan-400'
                              : 'bg-purple-950/60 text-purple-400'
                        }`}
                      >
                        {isVideo ? <Video size={16} /> : <Camera size={16} />}
                      </div>
                      <span className="text-[10px] font-semibold text-gray-300 truncate max-w-full">
                        {media.contact_name}
                      </span>
                    </div>
                  )}

                  {isIntimate && (
                    <span className="absolute top-1 right-1 z-10 text-[8px] px-1 bg-red-950/85 text-red-300 rounded border border-red-800 font-bold">
                      18+
                    </span>
                  )}
                  {!hasImage && !isGenerating && media.image_status === 'error' && (
                    <span
                      className="absolute top-1 left-1 z-10 text-[9px] px-1 bg-red-950/90 text-red-300 rounded border border-red-700/70 font-bold"
                      title={t('phone.vault.generate_failed', 'Could not generate photo.')}
                    >
                      !
                    </span>
                  )}
                </div>

                <div className="min-w-0">
                  <span className="text-[10px] text-gray-400 truncate block">
                    {media.caption || media.name}
                  </span>
                  <span className="text-[9px] font-mono tabular-nums text-gray-500 block">
                    {formatTimestamp(media.timestamp, clockFormat)}
                  </span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default PhonePhotosApp;
