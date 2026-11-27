import { useEffect, useRef } from 'react';
import { isTopEscapeLayer, registerEscapeLayer } from '../components/Common/MotionPrimitives';

export function useEscapeLayer(active, onEscape, debugLabel = 'escape-layer') {
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;

  useEffect(() => {
    if (!active) return undefined;
    const token = Symbol(debugLabel);
    const unregister = registerEscapeLayer(token);
    const onKeyDown = (e) => {
      if (e.key === 'Escape' && !e.defaultPrevented && isTopEscapeLayer(token)) {
        e.preventDefault();
        e.stopPropagation();
        onEscapeRef.current?.(e);
      }
    };
    window.addEventListener('keydown', onKeyDown, true);
    return () => {
      unregister();
      window.removeEventListener('keydown', onKeyDown, true);
    };
  }, [active, debugLabel]);
}
