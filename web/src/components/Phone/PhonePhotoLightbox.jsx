import {
  Camera,
  Check,
  Image as ImageIcon,
  Loader2,
  Play,
  RefreshCw,
  Sparkles,
  Video,
  X,
} from 'lucide-react';
import { isVideoMediaItem } from './phoneWallpapers';

const PhonePhotoLightbox = ({
  photo,
  sessionId,
  isImgGenActive,
  generatingPhotoId,
  deletingPhoto,
  photoActionError,
  isSelectedPhotoActiveWallpaper,
  onClosePhoto,
  onGenerateMediaPhoto,
  onSetPhotoAsWallpaper,
  onDeleteMedia,
  t,
}) => {
  if (!photo) return null;

  const isVideo = isVideoMediaItem(photo);
  const isGenerating =
    photo.image_status === 'generating' ||
    (photo.id && String(generatingPhotoId) === String(photo.id));
  const hasImage = Boolean(photo.image_url);

  return (
    <div
      data-phone-style="classic"
      className="absolute inset-0 hk-phone-lightbox z-30 flex flex-col p-4"
    >
      <div className="flex justify-between items-center border-b border-neutral-800 pb-2 mb-3 shrink-0">
        <span className="font-bold text-xs text-pink-300 truncate">{photo.contact_name}</span>
        <button
          type="button"
          onClick={onClosePhoto}
          className="p-1 text-gray-400 hover:text-gray-100 cursor-pointer"
        >
          <X size={16} />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar flex flex-col items-center justify-center p-3 text-center space-y-3 bg-neutral-950 border border-neutral-800 rounded-2xl min-h-0">
        {hasImage ? (
          <div className="relative w-full max-w-[270px] rounded-xl overflow-hidden border border-white/15 hk-phone-media-frame shadow-lg shrink-0">
            <img
              src={photo.image_url}
              alt={photo.caption || photo.name}
              className="w-full max-h-[340px] object-cover object-top"
            />
            {isVideo && (
              <span className="absolute inset-0 m-auto w-11 h-11 rounded-full hk-phone-play-badge flex items-center justify-center hk-phone-icon-glyph">
                <Play size={18} className="ml-0.5" />
              </span>
            )}
          </div>
        ) : isGenerating ? (
          <div className="w-full max-w-[240px] h-52 rounded-xl border border-pink-500/40 bg-pink-950/20 flex flex-col items-center justify-center gap-2 animate-pulse shrink-0">
            <Loader2 size={26} className="animate-spin text-pink-400" />
            <span className="text-xs font-semibold text-pink-200">
              {t('phone.vault.generating', 'Developing...')}
            </span>
          </div>
        ) : (
          <div className="w-16 h-16 rounded-full bg-pink-950/60 border border-pink-700/60 flex items-center justify-center text-pink-300 shrink-0">
            {isVideo ? <Video size={28} /> : <Camera size={28} />}
          </div>
        )}

        <h5 className="font-bold text-sm text-gray-100">{photo.name}</h5>
        <p className="text-xs text-gray-300 leading-relaxed max-w-xs italic bg-neutral-900/80 p-3 rounded-xl border border-neutral-800">
          &ldquo;{photo.caption}&rdquo;
        </p>

        {photoActionError && (
          <p className="text-[11px] text-red-300 bg-red-950/50 border border-red-800/60 rounded-lg px-2.5 py-1.5 max-w-xs">
            {photoActionError}
          </p>
        )}

        <div className="flex flex-wrap gap-1 justify-center">
          {photo.tags?.map((tag, i) => (
            <span key={i} className="text-[10px] px-2 py-0.5 bg-neutral-800 text-gray-400 rounded-full font-mono">
              #{tag}
            </span>
          ))}
        </div>

        <div className="flex flex-wrap items-center justify-center gap-2 pt-2">
          {photo.id && isImgGenActive && (
            <button
              type="button"
              disabled={isGenerating}
              onClick={() => onGenerateMediaPhoto(photo.id, { forceRegenerate: hasImage })}
              className="px-3 py-1.5 rounded-xl bg-pink-600/30 hover:bg-pink-600/50 text-pink-200 border border-pink-500/50 text-xs font-bold transition-colors cursor-pointer disabled:opacity-50 flex items-center gap-1.5"
            >
              {isGenerating ? (
                <Loader2 size={13} className="animate-spin" />
              ) : hasImage ? (
                <RefreshCw size={13} />
              ) : (
                <Sparkles size={13} />
              )}
              <span>
                {hasImage
                  ? t('phone.vault.regenerate', 'Regenerate')
                  : t('phone.vault.generate_photo', 'Generate Photo')}
              </span>
            </button>
          )}

          {hasImage && !isVideo && sessionId && (
            <button
              type="button"
              onClick={() => onSetPhotoAsWallpaper(photo)}
              className={`px-3 py-1.5 rounded-xl border text-xs font-bold transition-colors cursor-pointer flex items-center gap-1.5 ${
                isSelectedPhotoActiveWallpaper
                  ? 'bg-emerald-600/35 text-emerald-200 border-emerald-400/60'
                  : 'bg-sky-600/30 hover:bg-sky-600/50 text-sky-200 border-sky-500/50'
              }`}
            >
              {isSelectedPhotoActiveWallpaper ? <Check size={13} /> : <ImageIcon size={13} />}
              <span>
                {isSelectedPhotoActiveWallpaper
                  ? t('phone.vault.active_wallpaper', 'Active Wallpaper')
                  : t('phone.vault.set_wallpaper', 'Set as Wallpaper')}
              </span>
            </button>
          )}

          {photo.id && (
            <button
              type="button"
              disabled={deletingPhoto}
              onClick={() => onDeleteMedia(photo)}
              className="px-3 py-1.5 rounded-xl bg-red-950/60 hover:bg-red-900/70 text-red-300 border border-red-800/60 text-xs font-bold transition-colors cursor-pointer"
            >
              {deletingPhoto
                ? t('phone.vault.deleting', 'Deleting...')
                : t('phone.vault.delete_media', '🗑️ Delete Media')}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default PhonePhotoLightbox;
