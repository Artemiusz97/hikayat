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
