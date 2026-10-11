import { useState, type FormEvent } from "react";

export interface AuthUser {
  id: number;
  username: string;
}

type AuthMode = "login" | "register";

export default function AuthPage({ onAuthenticated }: { onAuthenticated: (user: AuthUser) => void }) {
  const [mode, setMode] = useState<AuthMode>("login");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setBusy(true);

    try {
      const response = await fetch(`/api/auth/${mode === "login" ? "login" : "register"}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: username.trim(), password }),
      });
      const result = await response.json().catch(() => ({}));

      if (!response.ok) {
        const detail = typeof result.detail === "string" ? result.detail : "Something went wrong. Please try again.";
        throw new Error(detail);
      }

      onAuthenticated({ id: result.id, username: result.username });
    } catch (requestError) {
      setError(requestError instanceof Error && requestError.message === "Failed to fetch"
        ? "Could not reach the server. Please try again in a moment."
        : requestError instanceof Error ? requestError.message : "Something went wrong. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  const registering = mode === "register";

  return (
    <main className="auth-page">
      <section className="glass auth-card fade-in" aria-labelledby="auth-title">
        <div className="auth-mark" aria-hidden="true">♠</div>
        <p className="auth-eyebrow">A little luck, a little skill</p>
        <h1 className="title-text auth-title" id="auth-title">Welcome to Bankroll</h1>
        <p className="auth-subtitle">Sign in to play, or create an account to get started.</p>

        <div className="auth-tabs" role="tablist" aria-label="Account access">
          <button type="button" role="tab" aria-selected={!registering} className={!registering ? "active" : ""} onClick={() => { setMode("login"); setError(""); }}>Sign in</button>
          <button type="button" role="tab" aria-selected={registering} className={registering ? "active" : ""} onClick={() => { setMode("register"); setError(""); }}>Create account</button>
        </div>

        <form className="auth-form" onSubmit={submit}>
          <label className="auth-field">
            <span className="label">Username</span>
            <input autoComplete="username" required maxLength={50} value={username} onChange={(event) => setUsername(event.target.value)} placeholder="Your username" />
          </label>
          <label className="auth-field">
            <span className="label">Password</span>
            <input autoComplete={registering ? "new-password" : "current-password"} required minLength={8} maxLength={1024} type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 8 characters" />
          </label>
          {error && <p className="error-text auth-error" role="alert">{error}</p>}
          <button className="btn btn-green auth-submit" type="submit" disabled={busy}>
            {busy ? "Please wait…" : registering ? "Create account" : "Sign in"}
          </button>
        </form>
      </section>
    </main>
  );
}
