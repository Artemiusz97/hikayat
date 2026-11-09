/**
 * Utilities for Hikayat session validation and lifecycle guards.
 */

/**
 * Validates whether a value is a legitimate active/persisted session identifier.
 * Temporary optimistic placeholders like 'embarking' or null/undefined are rejected.
 *
 * @param {string|number|null|undefined} id
 * @returns {boolean}
 */
export const isValidSessionId = (id) => {
  if (id === null || id === undefined || id === '') return false;
  if (id === 'embarking') return false;
  const num = Number(id);
  return Number.isInteger(num) && num > 0;
};

const ANOMALOUS_SCENARIO_ALIASES = new Set([
  'anomalous_incursions',
  'nsfw_gore_anomalous_incursions',
  'furry_anomalous_incursions',
  'nsfw_furry_gore_anomalous_incursions',
  'urban_anomalies',
  'anomalies',
  'anomaly',
  'anomalous',
  'incursions',
  'incursion',
  'mcb',
  'scp',
  'control',
  'anomalous_high_school',
  'anomalous_high',
  'anomalous_school',
  'anomaly_school',
  'anomalous_academy',
]);

/**
 * Mirrors Python `scenario_data.is_anomalous_incursions_scenario` so Anomalous Incursions
 * presets, Anomalous High hybrids, and legacy aliases (`urban_anomalies`, `scp`, etc.)
 * enable the Folklore Encyclopedia tab while keeping custom combinators separate.
 */
export const isAnomalousScenarioKey = (scenario) => {
  const s = String(scenario || '').trim().toLowerCase();
  if (!s || s.startsWith('custom')) return false;
  return s.includes('anomalous') || ANOMALOUS_SCENARIO_ALIASES.has(s);
};
