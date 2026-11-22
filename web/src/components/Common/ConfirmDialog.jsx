import { useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { AlertTriangle, X } from 'lucide-react';
import { AcrylicModal, MotionButton } from './MotionPrimitives';

const ConfirmDialog = ({
  isOpen,
  onClose,
  onConfirm,
  title,
  message,
  confirmLabel,
  cancelLabel,
  tone = 'danger',
  busy = false,
}) => {
  const { t } = useTranslation();
  const lastContentRef = useRef({ title, message, confirmLabel, cancelLabel, tone });
  if (isOpen) {
    lastContentRef.current = { title, message, confirmLabel, cancelLabel, tone };
  }
  const active = isOpen
    ? { title, message, confirmLabel, cancelLabel, tone }
    : lastContentRef.current;
  const isDanger = active.tone === 'danger';

  return (
    <AcrylicModal
      isOpen={isOpen}
      onClose={busy ? undefined : onClose}
      label={active.title || t('common.confirm', 'Confirm')}
      maxWidthClass="max-w-sm"
      zIndexClass="z-[80]"
      closeOnBackdrop={!busy}
    >
      <div className="px-4 py-3 border-b border-fantasy-border/35 flex items-center justify-between gap-2 shrink-0">
        <div className="flex items-center gap-2 min-w-0">
          <AlertTriangle
            size={16}
            className={isDanger ? 'text-red-400 shrink-0' : 'text-fantasy-accent shrink-0'}
          />
          <h3 className="font-rpg font-bold text-sm text-gray-100 truncate">
            {active.title || t('common.confirm', 'Confirm')}
          </h3>
        </div>
        <MotionButton
          onClick={onClose}
          disabled={busy}
          aria-label={t('common.close', 'Close')}
          className="hk-icon-btn h-7 min-w-7 shrink-0 disabled:opacity-40"
        >
          <X size={15} />
        </MotionButton>
      </div>

      <div className="px-4 py-3.5 text-xs text-gray-300 leading-relaxed">
        {active.message}
      </div>

      <div className="px-4 py-3 border-t border-fantasy-border/35 flex items-center justify-end gap-2 shrink-0">
        <MotionButton
          onClick={onClose}
          disabled={busy}
          className="px-3.5 py-1.5 rounded-lg border border-fantasy-border/60 text-xs font-medium text-gray-300 hover:text-white hover:bg-gray-500/10 disabled:opacity-40"
        >
          {active.cancelLabel || t('common.cancel', 'Cancel')}
        </MotionButton>
        <MotionButton
          onClick={onConfirm}
          disabled={busy}
          className={`px-3.5 py-1.5 rounded-lg text-xs font-bold transition-colors disabled:opacity-50 ${
            isDanger
              ? 'bg-red-600 hover:bg-red-500 text-white'
              : 'bg-fantasy-accent hover:bg-amber-400 text-black'
          }`}
        >
          {busy
            ? t('common.loading', 'Loading...')
            : active.confirmLabel || t('common.confirm', 'Confirm')}
        </MotionButton>
      </div>
    </AcrylicModal>
  );
};

export default ConfirmDialog;
