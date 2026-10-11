import type { SoundKey } from "@/audio/soundConfig";
import type { GameView } from "@/lib/blackjackApi";
import { isNatural } from "@/lib/scoring";

/**
 * SPECIAL-MESSAGE FRAMEWORK: what is announced when a round ends.
 *
 * Edit `ROUND_EVENTS` to change the banner text, add a subtitle line, attach a
 * sound (a key from audio/soundConfig.ts) or choose the visual effect.
 * `effect: "natural"` gives the gold banner, screen flash and card glow.
 */

export type RoundEventKey =
  | "playerNatural"
  | "dealerNatural"
  | "bothNatural"
  | "win"
  | "loss"
  | "push"
  | "bust"
  | "surrender";

export interface RoundEventDef {
  banner: string;
  /** Smaller line under the banner; null for none. */
  subtitle: string | null;
  /** Sound played when the result appears; null for none. */
  sfx: SoundKey | null;
  effect: "none" | "natural";
  /** Banner colour theme (matches `.result-banner.<tone>` in globals.css). */
  tone: "win" | "loss" | "push";
}

export const ROUND_EVENTS: Record<RoundEventKey, RoundEventDef> = {
  // TODO(message): final copy for natural blackjacks.
  playerNatural: { banner: "Blackjack!", subtitle: null, sfx: "blackjack.player", effect: "natural", tone: "win" },
  dealerNatural: { banner: "Dealer Blackjack", subtitle: null, sfx: "blackjack.dealer", effect: "natural", tone: "loss" },
  bothNatural: { banner: "Double Blackjack", subtitle: null, sfx: "blackjack.both", effect: "natural", tone: "push" },
  win: { banner: "You win!", subtitle: null, sfx: null, effect: "none", tone: "win" },
  loss: { banner: "You lose", subtitle: null, sfx: null, effect: "none", tone: "loss" },
  push: { banner: "Push", subtitle: null, sfx: null, effect: "none", tone: "push" },
  bust: { banner: "Bust!", subtitle: null, sfx: "bust", effect: "none", tone: "loss" },
  surrender: { banner: "Surrendered", subtitle: null, sfx: null, effect: "none", tone: "loss" },
};

/** Classify a finished round. */
export function getRoundEvent(view: GameView): RoundEventKey {
  if (view.result === "surrender") return "surrender";
  const playerNatural = isNatural(view.player_hand);
  const dealerNatural = isNatural(view.dealer_hand);
  if (playerNatural && dealerNatural) return "bothNatural";
  if (playerNatural) return "playerNatural";
  if (dealerNatural) return "dealerNatural";
  if (view.player_score > 21) return "bust";
  if (view.result === "win") return "win";
  if (view.result === "push") return "push";
  return "loss";
}
