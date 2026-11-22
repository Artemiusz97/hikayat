import { Component, Suspense, forwardRef, useEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion, useReducedMotion } from 'motion/react';
import { useTranslation } from 'react-i18next';

const _escapeLayerStack = [];

export const registerEscapeLayer = (token) => {
  _escapeLayerStack.push(token);
  return () => {
    const idx = _escapeLayerStack.lastIndexOf(token);
    if (idx !== -1) _escapeLayerStack.splice(idx, 1);
  };
};

export const isTopEscapeLayer = (token) =>
  _escapeLayerStack.length > 0 &&
  _escapeLayerStack[_escapeLayerStack.length - 1] === token;

const LazyChunkFallback = ({ onRetry }) => {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="fixed bottom-4 right-4 z-[90] hk-acrylic rounded-xl border border-red-500/40 px-4 py-3 shadow-2xl flex items-center gap-3 text-xs text-gray-200 max-w-xs"
    >
      <span className="flex-1">
        {t('common.chunk_load_error', 'Failed to load panel. Reload the page to refresh.')}
      </span>
      <button
        type="button"
        onClick={onRetry || (() => window.location.reload())}
        className="px-2.5 py-1 rounded-md bg-fantasy-accent text-black font-semibold shrink-0 hover:brightness-110 cursor-pointer"
      >
        {t('common.reload_page', 'Reload')}
      </button>
    </div>
  );
};

class LazyErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidUpdate(prevProps) {
    if (prevProps.open && !this.props.open && this.state.hasError) {
      this.setState({ hasError: false });
    }
  }

  render() {
    if (this.state.hasError) {
      if (!this.props.open) return null;
      return <LazyChunkFallback onRetry={() => window.location.reload()} />;
    }
    return this.props.children;
  }
}

export const LazyMount = ({ open, children }) => {
  const [mounted, setMounted] = useState(Boolean(open));
  useEffect(() => {
    if (open && !mounted) setMounted(true);
  }, [open, mounted]);
  if (!mounted && !open) return null;
  return (
    <LazyErrorBoundary open={Boolean(open)}>
      <Suspense fallback={null}>{children}</Suspense>
    </LazyErrorBoundary>
  );
};

export const SPRING_SNAPPY = {
  type: 'spring',
  stiffness: 520,
  damping: 32,
  mass: 0.7,
};

export const SPRING_PANEL = {
  type: 'spring',
  stiffness: 360,
  damping: 30,
  mass: 0.85,
};

export const EASE_OUT = [0.22, 1, 0.36, 1];

const VARIANT_CLASSES = {
  panel: 'hk-acrylic',
  reading: 'hk-acrylic-reading',
  pill: 'hk-acrylic-pill',
};

const getOriginVariants = (origin, reduced) => {
  if (reduced) {
    return {
      initial: { opacity: 0 },
      animate: { opacity: 1 },
      exit: { opacity: 0 },
    };
  }
  switch (origin) {
    case 'left':
      return {
        initial: { opacity: 0, x: -18, scale: 0.985 },
        animate: { opacity: 1, x: 0, scale: 1 },
        exit: { opacity: 0, x: -18, scale: 0.985 },
      };
    case 'right':
      return {
        initial: { opacity: 0, x: 18, scale: 0.985 },
        animate: { opacity: 1, x: 0, scale: 1 },
        exit: { opacity: 0, x: 18, scale: 0.985 },
      };
    case 'bottom':
      return {
        initial: { opacity: 0, y: 16, scale: 0.985 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: 16, scale: 0.985 },
      };
    case 'top':
      return {
        initial: { opacity: 0, y: -14, scale: 0.985 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: -14, scale: 0.985 },
      };
    case 'center':
    default:
      return {
        initial: { opacity: 0, y: 10, scale: 0.97 },
        animate: { opacity: 1, y: 0, scale: 1 },
        exit: { opacity: 0, y: 8, scale: 0.97 },
      };
  }
};

export const MotionButton = forwardRef(
  (
    {
      type = 'button',
      disabled = false,
      className = '',
      children,
      whileHover,
      whileTap,
      transition,
      ...rest
    },
    ref
  ) => {
    const reduced = useReducedMotion();
    const interactive = !disabled && !reduced;

    return (
      <motion.button
        ref={ref}
        type={type}
        disabled={disabled}
        whileTap={interactive ? (whileTap ?? { scale: 0.965 }) : undefined}
        whileHover={interactive ? (whileHover ?? { y: -1 }) : undefined}
        transition={transition ?? SPRING_SNAPPY}
        className={className}
        {...rest}
      >
        {children}
      </motion.button>
    );
  }
);
MotionButton.displayName = 'MotionButton';

export const AcrylicPanel = forwardRef(
  (
    {
      variant = 'panel',
      origin = 'center',
      className = '',
      children,
      transition,
      ...rest
    },
    ref
  ) => {
    const reduced = useReducedMotion();
    const surfaceClass = VARIANT_CLASSES[variant] || VARIANT_CLASSES.panel;
    const motionVars = getOriginVariants(origin, reduced);

    return (
      <motion.div
        ref={ref}
        initial={motionVars.initial}
        animate={motionVars.animate}
        exit={motionVars.exit}
        transition={
          transition ?? (reduced ? { duration: 0.16 } : SPRING_PANEL)
        }
        className={`${surfaceClass} ${className}`.trim()}
        {...rest}
      >
        {children}
      </motion.div>
    );
  }
);
AcrylicPanel.displayName = 'AcrylicPanel';

export const CollapsibleSection = ({ isOpen, children, className = '' }) => {
  const reduced = useReducedMotion();

  return (
    <AnimatePresence initial={false}>
      {isOpen && (
        <motion.div
          key="collapsible"
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          exit={{ height: 0, opacity: 0 }}
          transition={
            reduced
              ? { duration: 0.14 }
              : { duration: 0.24, ease: EASE_OUT }
          }
          className={`overflow-hidden ${className}`.trim()}
        >
          {children}
        </motion.div>
      )}
    </AnimatePresence>
  );
};

export const AcrylicModal = ({
  isOpen,
  onClose,
  label,
  maxWidthClass = 'max-w-lg',
  zIndexClass = 'z-50',
  children,
  className = '',
  closeOnBackdrop = true,
}) => {
  const reduced = useReducedMotion();
  const dialogRef = useRef(null);
  const previousFocusRef = useRef(null);
  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const token = Symbol('acrylic-modal');
    const unregister = registerEscapeLayer(token);

    previousFocusRef.current =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;

    const frame = requestAnimationFrame(() => {
      const node = dialogRef.current;
      if (node && !node.contains(document.activeElement)) {
        node.focus({ preventScroll: true });
      }
    });

    const handleKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        onCloseRef.current?.();
      }
    };
    window.addEventListener('keydown', handleKeyDown, true);

    return () => {
      unregister();
      cancelAnimationFrame(frame);
      window.removeEventListener('keydown', handleKeyDown, true);
      const prev = previousFocusRef.current;
      if (prev && typeof prev.focus === 'function' && prev.isConnected) {
        prev.focus({ preventScroll: true });
      }
    };
  }, [isOpen]);

  if (typeof document === 'undefined') return null;

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          data-motion="true"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: reduced ? 0.12 : 0.2, ease: EASE_OUT }}
          className={`fixed inset-0 ${zIndexClass} flex items-center justify-center p-3 sm:p-4 bg-black/65 backdrop-blur-sm overscroll-contain`}
          onClick={closeOnBackdrop ? () => onClose?.() : undefined}
        >
          <motion.div
            ref={dialogRef}
            role="dialog"
            aria-modal="true"
            aria-label={label}
            tabIndex={-1}
            initial={
              reduced
                ? { opacity: 0 }
                : { opacity: 0, scale: 0.96, y: 14 }
            }
            animate={
              reduced ? { opacity: 1 } : { opacity: 1, scale: 1, y: 0 }
            }
            exit={
              reduced
                ? { opacity: 0 }
                : { opacity: 0, scale: 0.96, y: 10 }
            }
            transition={reduced ? { duration: 0.14 } : SPRING_PANEL}
            onClick={(e) => e.stopPropagation()}
            className={`hk-acrylic relative w-full min-w-0 ${maxWidthClass} max-h-[calc(var(--app-height,100dvh)-2rem)] flex flex-col overflow-hidden overscroll-contain outline-none ${className}`.trim()}
          >
            {children}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
};
