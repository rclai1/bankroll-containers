# Frameworks: sound, special messages, timing, modes

Everything below is wired up but empty. Filling in the values listed here is all
that is needed; no component code has to change.

## 1. Sound (`src/audio/`)

| File | Purpose |
| --- | --- |
| `src/audio/soundConfig.ts` | **Edit this.** Every sound key with its `src` (URL path) and `volume`. `src: null` = silent. Also holds the variant selectors and their thresholds. |
| `src/audio/audioManager.ts` | Playback engine (one-shots, looping BGM with crossfade, mute, autoplay-unlock). No edits needed. |
| `src/audio/useSound.ts` | `play(key)` and `useBgm(key)` helpers used by components. |
| `src/components/MuteToggle.tsx` | Mute button (bottom-right); persists in localStorage. |

Audio files live in `src/assets/sfx/`. Link one in `src/audio/soundConfig.ts` by adding it to the `sfx` list (the path must be a literal `new URL("../assets/sfx/<file>", import.meta.url)`) and using `sfx.<name>()` in the `SOUNDS` entry. Music (`bgm.*`) loops from the start when it ends.

| Key (in `soundConfig.ts`) | Triggered from | Notes |
| --- | --- | --- |
| `bgm.menu` | `MainMenu.tsx` (`useBgm`) | Main menu music |
| `bgm.regular` / `bgm.daily` / `bgm.chaos` / `bgm.learning` / `bgm.gambling` | `Game.tsx` (`useBgm(MODES_BY_ID[mode].bgm)`) | Which key a mode uses is set by `bgm` in `src/config/modes.ts` |
| `menu.daily` / `menu.regular` / `menu.chaos` / `menu.learning` / `menu.gambling` | `MainMenu.tsx` button click | Which key a button uses is `clickSfx` in `src/config/modes.ts` |
| `menu.bubblePop` | `Scene.tsx` `pop()` | Bubble clicked |
| `card.deal` | `src/lib/roundSteps.ts` (every deal step) | |
| `card.flip` | `src/lib/roundSteps.ts` (every flip step) | Extra (not in the original list) |
| `money.withdraw` | `Game.tsx` `run("bet")` | Extra; bet leaves the bankroll |
| `deal.low` / `deal.mid` / `deal.high` | `Game.tsx` bet form submit via `selectDealSound(bet, bankroll)` | Tune `DEAL_SOUND_THRESHOLDS` (bet as a fraction of total money) |
| `hit.default` / `hit.highBet` / `hit.hardHand` | `Game.tsx` Hit button via `selectHitSound(...)` | Tune `HIT_SOUND_THRESHOLDS`; add more variants/`TODO(sfx)` in `selectHitSound` |
| `stand` | `Game.tsx` Stand button | |
| `double` / `surrender` | `Game.tsx` Double Down / Surrender buttons | |
| `nextRound` | `Game.tsx` "Next round" / "new game" button | |
| `blackjack.player` / `blackjack.dealer` / `blackjack.both` | `Game.tsx` `settleRound`, via `ROUND_EVENTS[...].sfx` | Natural blackjack for the player, the dealer, or both |
| `bust` | `Game.tsx` `settleRound`, via `ROUND_EVENTS.bust.sfx` | The player busts |
| `gacha.nothing` / `gacha.dupe` / `gacha.hit` | `CardShop.tsx` `openCase()` | A pack with no skin / a skin you already own (refunded) / a new skin; plays when the result arrives, as the reveal pop-up opens |

To add a new sound: add a key to `SOUNDS` in `soundConfig.ts`, then call
`play("your.key")` where it should fire (or reference it from a `sfx` field in
`messages.ts` / `modes.ts`).

## 2. Special messages (`src/config/messages.ts`)

`ROUND_EVENTS` has one entry per round outcome. Fields per entry:

- `banner`: main text. **Natural blackjack copy is a placeholder** (`playerNatural`, `dealerNatural`, `bothNatural`; marked `TODO(message)`).
- `subtitle`: optional smaller line under the banner (`null` = none).
- `sfx`: a `SoundKey` played when the result appears (naturals use `blackjack.player/dealer/both`, a bust uses `bust`; others `null`).
- `effect`: `"natural"` enables the gold banner, screen flash and card glow.
- `tone`: `win` / `loss` / `push` banner colour.

`getRoundEvent(view)` in the same file decides which entry applies.

## 3. Timing (`src/config/timing.ts`)

All round pacing (bet withdrawal delay, deal interval, flip gaps, pause between
the dealer flipping and drawing, settle pause). Fixed values; independent of bet
size. The sequence itself is built in `src/lib/roundSteps.ts`.

## 4. Modes (`src/config/modes.ts`)

Per mode: `label`, `enabled` (only `regular` is true), `bgm` key, `clickSfx` key,
button `style`. Set `enabled: true` once a mode exists, and handle `mode` in
`Game.tsx` (currently every mode would run the regular rules).

## 5. CPU players (backend `cpu_agents.py` + `cpu_turn` endpoint)

The UI shows CPUs: Regular Mode asks for 0, 1 or 2 CPUs in a pop-up (`MainMenu.tsx`, `CPU_COUNTS` in `src/config/layout.ts`), CPU 1 sits on the left edge of the table and CPU 2 on the right (`CpuSeat.tsx`). The API supports them
(`POST /games {"cpu_count": 0-2}`) and Google Gemini can drive them (`CPU_AGENT=gemini`, key `GEMINI_KEY` in the project `.env`).

- `backend/cpu_agents.py`: the agent seam. `GeminiCpuAgent` keeps one stored Gemini conversation per CPU seat (chained with `previous_interaction_id`, bets and actions in the same chain, restarted after `GEMINI_MAX_CHAIN_TURNS`); all seats share one client. If Gemini is unavailable the seat falls back to the default agent. Timing constants `CPU_MIN_ACTION_SECONDS` (3) and `CPU_MAX_ACTION_SECONDS` (15); at 15 s a CPU stands (bets fall back to the minimum).
- Turn flow: after the human's last action the response has `status: "playing"` and `current_player` set to a CPU. `Game.tsx` (`driveCpus`) then calls `cpuTurn(game_id)` repeatedly (each call = one CPU action, 3-15 s) until `status === "finished"`, showing "Thinking…" under that seat and animating each action with `cpuTurnSteps` in `src/lib/roundSteps.ts`; the dealer's events arrive in the last response. If a call fails, a "Retry CPU turn" button appears. Sizes: `CARD_SCALE` in `src/config/layout.ts`.
- `GameView.players` / `events` carry everything needed to render CPU seats and animate their actions.
- Gemini tuning knobs (env vars, all optional; defaults in `backend/cpu_agents.py`): `GEMINI_THINKING_LEVEL` (`minimal|low|medium|high|default`, default `low`), `GEMINI_SDK_RETRIES` (SDK re-sends per call, default `0`), `CPU_AGENT_LOG_LEVEL` (default `INFO`) and `CPU_AGENT_LOG_HTTP=0` to hide the per-request HTTP log lines. Each Gemini call logs its latency; each HTTP request the SDK actually sends is logged too, so retries are visible.
- In order to enable Gemini Players, the `.env` must be configured so that `CPU_AGENT="gemini"` and there must be a Gemini API key.
