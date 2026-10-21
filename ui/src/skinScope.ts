/** The skin panel must never silently send a whole-image edit. */
export function skinStrengthOptions(): { channel: "skin" } {
  return { channel: "skin" };
}

export function skinMaskUnavailable(counts?: Record<string, number>): boolean {
  return counts?.skin === 0;
}
