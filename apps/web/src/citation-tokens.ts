// Rendering only: the backend validates reserved syntax and final bindings.
export function citationParts(text: string) {
  return text.split(/(\[E[1-9][0-9]*\])/g);
}

export function citationForPart<T extends { label: string }>(
  part: string,
  citations: readonly T[],
) {
  if (!/^\[E[1-9][0-9]*\]$/.test(part)) return undefined;
  return citations.find((citation) => `[${citation.label}]` === part);
}
