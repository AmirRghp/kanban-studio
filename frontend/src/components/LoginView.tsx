"use client";

import { useState, type FormEvent } from "react";
import { signIn } from "@/lib/api";

type LoginViewProps = {
  onSignedIn: (username: string) => void;
};

export const LoginView = ({ onSignedIn }: LoginViewProps) => {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const user = await signIn(username, password);
      onSignedIn(user.username);
    } catch {
      setError("Invalid username or password");
      setIsSubmitting(false);
    }
  };

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-5 rounded-[32px] border border-[var(--stroke)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow)]"
        data-testid="login-form"
      >
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--gray-text)]">
            Project Management MVP
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold text-[var(--navy-dark)]">
            Sign in
          </h1>
        </div>

        <label className="block space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--gray-text)]">
            Username
          </span>
          <input
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            aria-label="Username"
            autoComplete="username"
            className="w-full rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm font-medium text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
          />
        </label>

        <label className="block space-y-2">
          <span className="text-xs font-semibold uppercase tracking-[0.2em] text-[var(--gray-text)]">
            Password
          </span>
          <input
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            aria-label="Password"
            autoComplete="current-password"
            className="w-full rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm font-medium text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
          />
        </label>

        {error && (
          <p
            role="alert"
            data-testid="login-error"
            className="text-sm font-semibold text-[var(--secondary-purple)]"
          >
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={isSubmitting}
          className="w-full rounded-full bg-[var(--secondary-purple)] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white transition hover:brightness-110 disabled:opacity-60"
        >
          Sign in
        </button>
      </form>
    </main>
  );
};
