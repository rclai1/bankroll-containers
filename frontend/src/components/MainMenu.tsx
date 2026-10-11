import { useEffect, useState } from "react";
import { MODES, type ModeDef, type ModeId } from "@/config/modes";
import { CPU_COUNTS, type CpuCount } from "@/config/layout";
import { play, useBgm } from "@/audio/useSound";
import { formatMoney } from "./Money";
import { getHighScores, type HighScoreEntry } from "@/lib/blackjackApi";

export default function MainMenu({
  onStart,
  username,
  onSignOut,
  onShop,
}: {
  onStart: (mode: ModeId, cpuCount: CpuCount) => void;
  username: string;
  onSignOut: () => void;
  onShop: () => void;
}) {
  useBgm("bgm.menu");
  const [tab, setTab] = useState<"play" | "leaderboard">("play");
  const [scores, setScores] = useState<HighScoreEntry[]>([]);
  const [loadingScores, setLoadingScores] = useState(false);
  const [leaderboardError, setLeaderboardError] = useState<string | null>(null);

  async function openLeaderboard() {
    setTab("leaderboard");
    setLoadingScores(true);
    setLeaderboardError(null);
    try {
      setScores(await getHighScores());
    } catch (error) {
      setLeaderboardError(error instanceof Error ? error.message : "Could not load leaderboard");
    } finally {
      setLoadingScores(false);
    }
  }

  // The mode waiting for a CPU count, and the count chosen in the pop-up.
  const [pending, setPending] = useState<ModeDef | null>(null);
  const [cpuCount, setCpuCount] = useState<CpuCount>(0);

  useEffect(() => {
    if (!pending) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPending(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pending]);

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <div className="glass fade-in flex w-full max-w-3xl flex-col items-center gap-8 px-8 py-12 sm:px-20">
        <div className="menu-account">
          <span>Playing as <strong>{username}</strong></span>
          <button className="btn-link" onClick={onSignOut}>Sign out</button>
        </div>
        <h1 className="title-text text-5xl sm:text-7xl">Bankroll</h1>
        {tab === "play" ? (
        <div className="flex w-72 gap-3" aria-label="Main menu actions">
            <button className="btn btn-green flex-1 px-2" onClick={() => {
              play("menu.daily");
              onStart("daily", 0);
            }}>Play</button>
            <button className="btn btn-orange flex flex-1 items-center justify-center px-2 text-center" onClick={openLeaderboard}>Leaderboard</button>
          </div>
        ) : (
          <button className="btn btn-orange w-72" onClick={() => setTab("play")}>Back</button>
        )}
        {tab === "play" ? (
          <nav className="flex w-72 flex-col gap-3" aria-label="Game modes">
            {MODES.filter((mode) => mode.id !== "daily").map((mode) => (
              <button
                key={mode.id}
                className={`btn btn-${mode.style} mode-button`}
                disabled={!mode.enabled}
                onClick={() => {
                  play(mode.clickSfx);
                  if (mode.id === "gambling") onShop();
                  else if (mode.askCpuCount) setPending(mode);
                  else onStart(mode.id, 0);
                }}
              >
                {mode.label}
                {!mode.enabled && <span className="mode-tag">Coming soon</span>}
              </button>
            ))}
          </nav>
        ) : (
          <section className="w-full" aria-label="Leaderboard">
            {loadingScores ? <p className="text-center">Loading scores…</p> : leaderboardError ? (
              <p className="error-text text-center" role="alert">{leaderboardError}</p>
            ) : scores.length === 0 ? (
              <p className="text-center">No high scores yet.</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-white/30">
                      <th scope="col" className="px-4 py-3">Place</th>
                      <th scope="col" className="px-4 py-3">Username</th>
                      <th scope="col" className="px-4 py-3 text-right">High score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {scores.slice(0, 10).map((entry, index) => (
                      <tr key={entry.id} className="border-b border-white/15">
                        <td className="px-4 py-3">{index + 1}</td>
                        <td className="px-4 py-3">{entry.username}</td>
                        <td className="px-4 py-3 text-right">{formatMoney(entry.score)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        )}
      </div>

      {pending && (
        <div className="modal-backdrop" onClick={() => setPending(null)}>
          <div
            className="glass modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby="cpu-count-title"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 id="cpu-count-title" className="title-text modal-title">
              How many CPUs?
            </h2>
            <div className="cpu-options" role="radiogroup" aria-labelledby="cpu-count-title">
              {CPU_COUNTS.map((n) => (
                <button
                  key={n}
                  role="radio"
                  aria-checked={cpuCount === n}
                  className={`btn cpu-option${cpuCount === n ? " selected" : ""}`}
                  onClick={() => setCpuCount(n)}
                >
                  {n}
                </button>
              ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-orange btn-md" onClick={() => setPending(null)}>
                Back
              </button>
              <button className="btn btn-green btn-md" autoFocus onClick={() => onStart(pending.id, cpuCount)}>
                Start Game
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
