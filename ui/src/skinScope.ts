/** The skin panel must never silently send a whole-image edit. */
export function skinStrengthOptions(): { channel: "skin" } {
  return { channel: "skin" };
}

export function skinMaskUnavailable(counts?: Record<string, number>): boolean {
  return counts?.skin === 0;
}

export interface SkinEdit { strength?: number; detail?: number; broad?: number; radius?: number }
/** A UI edit is a patch, not a stale snapshot of the whole document. */
export function skinEditOptions(patch: SkinEdit) {
  return {
    channel: "skin" as const,
    interactionKey: Object.keys(patch).sort().join(","),
    ...(patch.radius === undefined ? {} : {radius: patch.radius}),
    ...(patch.detail === undefined ? {} : {detailGain: patch.detail}),
    ...(patch.broad === undefined ? {} : {broadGain: patch.broad}),
  };
}
export function skinMaskReady(channels?: string[], counts?: Record<string, number>): boolean {
  return !!channels?.includes("skin") && typeof counts?.skin === "number" && counts.skin > 0;
}
