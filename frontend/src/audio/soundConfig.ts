/**
 * SOUND FRAMEWORK: the one file to edit to change which sound plays when.
 *
 * Audio files live in `src/assets/sfx/`. Link one with `sfx("<file name>")`
 * below (the file name must be written out literally so the bundler can find
 * and ship it). `null` means "no sound" and every call to play it is a silent
 * no-op. `volume` is 0..1.
 *
 * Keys starting with `bgm.` loop (from the start again when the file ends) and
 * are played through `playBgm`; all others are one-shots. See
 * docs/FRAMEWORKS.md for where each key is triggered.
 */

export interface SoundDef {
  src: string | null;
  volume: number;
}

const sound = (src: string | null = null, volume = 0.7): SoundDef => ({ src, volume });

// `new URL("<literal path>", import.meta.url)` is how Next bundles a file
// from src/ and gives back its public URL. One helper call per file, so the
// path has to stay a string literal in each line below.
const sfx = {
  are_you_sure: () => new URL("../assets/sfx/are_you_sure.mp3", import.meta.url).href,
  bubble_pop: () => new URL("../assets/sfx/bubble_pop.mp3", import.meta.url).href,
  dire_dire_docks: () => new URL("../assets/sfx/dire_dire_docks.mp3", import.meta.url).href,
  fortnite_knocked: () => new URL("../assets/sfx/fortnite-knocked-made-with-Voicemod.mp3", import.meta.url).href,
  frutiger: () => new URL("../assets/sfx/frutiger.mp3", import.meta.url).href,
  lmk: () => new URL("../assets/sfx/lmk.mp3", import.meta.url).href,
  metal_pipe: () => new URL("../assets/sfx/metal_pipe.mp3", import.meta.url).href,
  mii_maker: () => new URL("../assets/sfx/mii_maker_wiiU.mp3", import.meta.url).href,
  monkeys: () => new URL("../assets/sfx/monkeys.mp3", import.meta.url).href,
  playing_card1: () => new URL("../assets/sfx/playing_card1.mp3", import.meta.url).href,
  playing_card2: () => new URL("../assets/sfx/playing_card2.mp3", import.meta.url).href,
  sad_trumpet: () => new URL("../assets/sfx/sad-trumpet.mp3", import.meta.url).href,
  siu: () => new URL("../assets/sfx/siu.mp3", import.meta.url).href,
  wii_click: () => new URL("../assets/sfx/wii_click.mp3", import.meta.url).href,
  wii_party: () => new URL("../assets/sfx/wii_party.mp3", import.meta.url).href,
  xp_shutdown: () => new URL("../assets/sfx/xp_shutdown.mp3", import.meta.url).href,
  xp_startup: () => new URL("../assets/sfx/xp_startup.mp3", import.meta.url).href,
  yippee: () => new URL("../assets/sfx/yippee.mp3", import.meta.url).href,
} as const;

export const SOUNDS = {
  // --- Background music (one per screen/mode; mapping lives in config/modes.ts) ---
  "bgm.menu": sound(sfx.wii_party(), 0.4),
  "bgm.regular": sound(sfx.mii_maker(), 0.4),
  "bgm.daily": sound(sfx.dire_dire_docks(), 0.4),
  "bgm.chaos": sound(null, 0.4), // no file yet
  "bgm.learning": sound(sfx.monkeys(), 0.4),
  "bgm.gambling": sound(null, 0.4), // no file yet

  // --- Main menu ---
  "menu.daily": sound(),
  "menu.regular": sound(),
  "menu.chaos": sound(),
  "menu.learning": sound(),
  "menu.gambling": sound(),
  "menu.bubblePop": sound(sfx.bubble_pop()),

  // --- Cards / money (triggered from the round timeline) ---
  "card.deal": sound(sfx.playing_card2()),
  "card.flip": sound(sfx.playing_card1()),
  // TODO(sfx): src/assets/sfx/money.mp3 is not in the folder yet; add it with sfx() above.
  "money.withdraw": sound(),

  // --- Deal button: variant picked by selectDealSound (bet size) ---
  "deal.low": sound(),
  "deal.mid": sound(),
  "deal.high": sound(),

  // --- Hit button: variant picked by selectHitSound (bet size / hand) ---
  "hit.default": sound(sfx.frutiger()),
  "hit.highBet": sound(sfx.are_you_sure()),
  "hit.hardHand": sound(sfx.are_you_sure()),

  // --- Other buttons ---
  stand: sound(sfx.wii_click()),
  double: sound(sfx.metal_pipe()), // Double Down button
  surrender: sound(sfx.xp_shutdown()), // Surrender button
  nextRound: sound(sfx.xp_startup()),

  // --- Round results (see config/messages.ts) ---
  bust: sound(sfx.lmk()),
  // TODO(sfx): fah_short.mp3 and fah_long.mp3 are not in the folder yet.
  "blackjack.dealer": sound(), // dealer natural blackjack (fah_short)
  "blackjack.player": sound(sfx.siu(), 0.9), // player natural blackjack
  "blackjack.both": sound(), // both have a natural (fah_long)

  // --- Gacha / card shop (not built yet; sounds are ready for it) ---
  "gacha.nothing": sound(sfx.sad_trumpet()),
  "gacha.dupe": sound(sfx.fortnite_knocked()),
  "gacha.hit": sound(sfx.yippee()),
} satisfies Record<string, SoundDef>;

export type SoundKey = keyof typeof SOUNDS;

// ---------------------------------------------------------------------------
// Variant selectors. Tune the thresholds here.
// ---------------------------------------------------------------------------

/** Bet as a fraction of the player's total money (bankroll + bet) at which the deal sound escalates. */
export const DEAL_SOUND_THRESHOLDS = { mid: 0.2, high: 0.5 } as const;

export function selectDealSound(bet: number, bankrollBeforeBet: number): SoundKey {
  const fraction = bankrollBeforeBet > 0 ? bet / bankrollBeforeBet : 0;
  if (fraction >= DEAL_SOUND_THRESHOLDS.high) return "deal.high";
  if (fraction >= DEAL_SOUND_THRESHOLDS.mid) return "deal.mid";
  return "deal.low";
}

/** Bet fraction / hand total at which the hit sound switches away from the default. */
export const HIT_SOUND_THRESHOLDS = { highBetFraction: 0.5, hardHandScore: 17 } as const;

export function selectHitSound(ctx: {
  bet: number;
  bankrollBeforeBet: number;
  playerScore: number;
}): SoundKey {
  // TODO(sfx): more variants by hand (soft hands, 11 or less, etc.) if wanted.
  const fraction = ctx.bankrollBeforeBet > 0 ? ctx.bet / ctx.bankrollBeforeBet : 0;
  if (fraction >= HIT_SOUND_THRESHOLDS.highBetFraction) return "hit.highBet";
  if (ctx.playerScore >= HIT_SOUND_THRESHOLDS.hardHandScore) return "hit.hardHand";
  return "hit.default";
}
