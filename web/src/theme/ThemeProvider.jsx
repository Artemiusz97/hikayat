import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { THEMES, DEFAULT_THEME, resolveScenarioTheme } from './themes';

const STORAGE_KEY = 'hikayat_theme_mode';
const ThemeContext = createContext(null);

const readStoredMode = () => {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === 'auto' || (v && THEMES[v])) return v;
  } catch {
    // storage unavailable (private mode) – fall through
  }
  return 'auto';
};

const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;

/** Writes the theme onto <html> so CSS variables cascade everywhere (incl. portals). */
const paintTheme = (id) => {
  const root = document.documentElement;
  const theme = THEMES[id] || THEMES[DEFAULT_THEME];
  root.dataset.theme = id;
  root.dataset.scheme = theme.scheme;
  const meta = document.querySelector('meta[name="theme-color"]');
  if (meta) meta.setAttribute('content', theme.swatch[0]);
};

/**
 * Animate a theme change. Uses a circular View Transition reveal from the
 * pointer origin when supported; otherwise swaps instantly.
 */
const transitionTheme = (id, origin) => {
  const root = document.documentElement;
  if (root.dataset.theme === id) return;
  if (!document.startViewTransition || prefersReducedMotion()) {
    paintTheme(id);
    return;
  }
  // Automatic (scenario-driven) changes: gentle default crossfade, no reveal.
  if (!origin) {
    document.startViewTransition(() => paintTheme(id));
    return;
  }
  const { x, y } = origin;
  const radius = Math.hypot(Math.max(x, window.innerWidth - x), Math.max(y, window.innerHeight - y));
  root.classList.add('theme-transitioning');
  const vt = document.startViewTransition(() => paintTheme(id));
  vt.ready
    .then(() => {
      root.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 650, easing: 'cubic-bezier(0.22, 1, 0.36, 1)', pseudoElement: '::view-transition-new(root)' }
      );
    })
    .catch(() => {});
  vt.finished.finally(() => root.classList.remove('theme-transitioning'));
};

export const ThemeProvider = ({ children }) => {
  const [mode, setModeState] = useState(readStoredMode);
  const [scenarioSource, setScenarioSource] = useState(null);
  const originRef = useRef(null);

  const scenarioTheme = useMemo(() => resolveScenarioTheme(scenarioSource), [scenarioSource]);
  const activeTheme = mode === 'auto' ? scenarioTheme : mode;

  // First paint and the initial session hydration (≈1.5s): no animation.
  const firstPaint = useRef(true);
  const mountedAt = useRef(typeof performance !== 'undefined' ? performance.now() : 0);
  useEffect(() => {
    const settling = typeof performance !== 'undefined' && performance.now() - mountedAt.current < 1500;
    if (firstPaint.current || (settling && !originRef.current)) {
      firstPaint.current = false;
      paintTheme(activeTheme);
      return;
    }
    transitionTheme(activeTheme, originRef.current);
    originRef.current = null;
  }, [activeTheme]);

  const setMode = useCallback((next, event) => {
    if (event && typeof event.clientX === 'number' && (event.clientX || event.clientY)) {
      originRef.current = { x: event.clientX, y: event.clientY };
    } else if (event?.currentTarget?.getBoundingClientRect) {
      const r = event.currentTarget.getBoundingClientRect();
      originRef.current = { x: r.left + r.width / 2, y: r.top + r.height / 2 };
    }
    setModeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      // ignore persistence failures
    }
  }, []);

  /** Views report the scenario they are showing (session, active slot, or null). */
  const setScenarioContext = useCallback((source) => {
    setScenarioSource((prev) => {
      const key = (s) => (s ? `${s.scenario || ''}|${JSON.stringify(s.scenario_tags || s.tags || '')}|${s.scenario_display_name || ''}` : '');
      return key(prev) === key(source) ? prev : source;
    });
  }, []);

  const value = useMemo(
    () => ({ mode, setMode, activeTheme, scenarioTheme, setScenarioContext, themes: THEMES }),
    [mode, setMode, activeTheme, scenarioTheme, setScenarioContext]
  );

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
};

export const useTheme = () => {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error('useTheme must be used inside <ThemeProvider>');
  return ctx;
};

/** Convenience hook: register the scenario a view is rendering. */
export const useScenarioTheme = (source) => {
  const { setScenarioContext } = useTheme();
  useEffect(() => {
    setScenarioContext(source || null);
  }, [source, setScenarioContext]);
};
