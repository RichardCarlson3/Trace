// Keep explicit provider syntax and identifiers intact. Plain text is case-insensitive;
// OpenAlex's default stemmed search handles singular/plural word forms.
function isPlainText(query: string) {
  return (
    /^[\p{L}\p{M}\p{N}\s'’–—-]+$/u.test(query) &&
    !/\b(AND|OR|NOT)\b/.test(query) &&
    !/^W[0-9]+$/i.test(query)
  );
}

export function normalizeSearchQuery(query: string) {
  const trimmed = query.trim();
  return isPlainText(trimmed)
    ? trimmed.replace(/\s+/g, " ").toLowerCase()
    : trimmed;
}

export function fuzzySearchQuery(query: string): string | null {
  if (!isPlainText(query)) return null;
  const words = query.split(/\s+/);
  if (words.length > 24) return null;
  let changed = false;
  const fuzzy = words
    .map((word) => {
      // Do not fuzz numbers, identifiers, very short words, or punctuation.
      if (!/^[\p{L}\p{M}]+$/u.test(word) || word.length < 4) return word;
      changed = true;
      return `${word}~${word.length >= 6 ? 2 : 1}`;
    })
    .join(" ");
  return changed && fuzzy.length <= 300 ? fuzzy : null;
}
