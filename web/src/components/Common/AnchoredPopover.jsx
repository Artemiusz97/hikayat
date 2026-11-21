import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { isTopEscapeLayer, registerEscapeLayer } from './MotionPrimitives';

const MARGIN = 8;
const PopoverTreeContext = createContext(null);

/**
 * Viewport-aware popover. Renders into <body> with fixed positioning so it can
 * never be clipped by sidebars, scroll containers or the screen edge. It flips
 * above the anchor when there is not enough room below and caps its height to
 * the visible viewport (respecting mobile browser chrome via visualViewport).
 */
const AnchoredPopover = ({
  anchorRef,
  open,
  onClose,
  width = 320,
  align = 'end', // 'start' | 'end'
  label,
  className = '',
  children,
}) => {
  const popRef = useRef(null);
  const [style, setStyle] = useState({ visibility: 'hidden' });
  const parentCtx = useContext(PopoverTreeContext);
  const depth = parentCtx ? parentCtx.depth + 1 : 0;
  const childCheckersRef = useRef(new Set());

  const containsTarget = useCallback((target) => {
    if (!target) return false;
    if (popRef.current?.contains(target)) return true;
    for (const fn of childCheckersRef.current) {
      if (fn(target)) return true;
    }
    return false;
  }, []);

  useEffect(() => {
    if (!open || !parentCtx?.registerChild) return undefined;
    return parentCtx.registerChild(containsTarget);
  }, [open, parentCtx, containsTarget]);

  const treeApi = useMemo(
    () => ({
      depth,
      registerChild: (fn) => {
        childCheckersRef.current.add(fn);
        return () => childCheckersRef.current.delete(fn);
      },
    }),
    [depth]
  );

  const place = useCallback(() => {
    const anchor = anchorRef?.current;
    if (!anchor) return;
    const vv = window.visualViewport;
    const vw = vv ? vv.width : window.innerWidth;
    const vh = vv ? vv.height : window.innerHeight;
    const r = anchor.getBoundingClientRect();
    const w = Math.min(width, vw - MARGIN * 2);
    let left = align === 'start' ? r.left : r.right - w;
    left = Math.max(MARGIN, Math.min(left, vw - w - MARGIN));

    const spaceBelow = vh - r.bottom - MARGIN * 2;
    const spaceAbove = r.top - MARGIN * 2;
    const popH = popRef.current?.scrollHeight || 0;
    const flip = popH > spaceBelow && spaceAbove > spaceBelow;
    const next = {
      position: 'fixed',
      left,
      width: w,
      maxHeight: Math.max(160, flip ? spaceAbove : spaceBelow),
      zIndex: 1000 + depth * 10,
      visibility: 'visible',
      transformOrigin: `${align === 'start' ? 'left' : 'right'} ${flip ? 'bottom' : 'top'}`,
    };
    if (flip) next.bottom = vh - r.top + MARGIN;
    else next.top = r.bottom + MARGIN;
    setStyle(next);
  }, [anchorRef, width, align, depth]);

  useLayoutEffect(() => {
    if (!open) return undefined;
    place();
    // Second pass once content has measured.
    const id = requestAnimationFrame(place);
    return () => cancelAnimationFrame(id);
  }, [open, place]);

  const onCloseRef = useRef(onClose);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    if (!open) return undefined;
    const token = Symbol('anchored-popover');
    const unregister = registerEscapeLayer(token);
    const onDown = (e) => {
      if (containsTarget(e.target) || anchorRef?.current?.contains(e.target)) return;
      onCloseRef.current?.();
    };
    const onKey = (e) => {
      if (e.key !== 'Escape' || e.defaultPrevented) return;
      if (childCheckersRef.current.size > 0 || !isTopEscapeLayer(token)) return;
      e.preventDefault();
      e.stopPropagation();
      onCloseRef.current?.();
    };
    const onReflow = () => place();
    document.addEventListener('pointerdown', onDown);
    window.addEventListener('keydown', onKey, true);
    window.addEventListener('resize', onReflow);
    window.addEventListener('scroll', onReflow, true);
    window.visualViewport?.addEventListener('resize', onReflow);
    return () => {
      unregister();
      document.removeEventListener('pointerdown', onDown);
      window.removeEventListener('keydown', onKey, true);
      window.removeEventListener('resize', onReflow);
      window.removeEventListener('scroll', onReflow, true);
      window.visualViewport?.removeEventListener('resize', onReflow);
    };
  }, [open, place, anchorRef, containsTarget]);

  if (!open) return null;

  return createPortal(
    <div
      ref={popRef}
      role="dialog"
      aria-label={label}
      style={style}
      className={`hk-popover hk-acrylic overflow-y-auto overscroll-contain custom-scrollbar shadow-2xl ${className}`}
    >
      <PopoverTreeContext.Provider value={treeApi}>
        {children}
      </PopoverTreeContext.Provider>
    </div>,
    document.body
  );
};

export default AnchoredPopover;
