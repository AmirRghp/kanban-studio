"use client";

import { useState, type FormEvent } from "react";
import { register, signIn } from "@/lib/api";

type Mode = "sign-in" | "register";

type LoginViewProps = {
  onSignedIn: (username: string) => void;
};

export const LoginView = ({ onSignedIn }: LoginViewProps) => {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const isRegister = mode === "register";

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSubmitting(true);
    setError(null);
    try {
      const user = isRegister
        ? await register(username, password)
        : await signIn(username, password);
      onSignedIn(user.username);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : "Something went wrong. Try again."
      );
      setIsSubmitting(false);
    }
  };

  const switchTo = (next: Mode) => {
    setMode(next);
    setError(null);
  };

  const tabClasses = (active: boolean) =>
    `flex-1 rounded-full px-4 py-2 text-xs font-semibold uppercase tracking-wide transition ${
      active
        ? "bg-[var(--navy-dark)] text-white"
        : "text-[var(--gray-text)] hover:text-[var(--navy-dark)]"
    }`;

  return (
    <main className="flex min-h-screen items-center justify-center px-6">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm space-y-5 rounded-[32px] border border-[var(--stroke)] bg-[var(--surface-strong)] p-8 shadow-[var(--shadow)]"
        data-testid="login-form"
      >
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.35em] text-[var(--gray-text)]">
            Kanban Studio
          </p>
          <h1 className="mt-3 font-display text-3xl font-semibold text-[var(--navy-dark)]">
            {isRegister ? "Create your account" : "Sign in"}
          </h1>
        </div>

        <div
          className="flex gap-1 rounded-full bg-[var(--surface)] p-1"
          role="tablist"
          aria-label="Authentication mode"
        >
          <button
            type="button"
            role="tab"
            aria-selected={!isRegister}
            onClick={() => switchTo("sign-in")}
            className={tabClasses(!isRegister)}
          >
            Sign in
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={isRegister}
            onClick={() => switchTo("register")}
            className={tabClasses(isRegister)}
          >
            Create account
          </button>
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
            autoComplete={isRegister ? "new-password" : "current-password"}
            className="w-full rounded-xl border border-[var(--stroke)] bg-white px-3 py-2 text-sm font-medium text-[var(--navy-dark)] outline-none transition focus:border-[var(--primary-blue)]"
          />
          {isRegister && (
            <span className="text-xs text-[var(--gray-text)]">
              At least 8 characters. Usernames are 3-30 letters, numbers, hyphens or
              underscores.
            </span>
          )}
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
          disabled={isSubmitting || !username.trim() || !password}
          className="w-full rounded-full bg-[var(--secondary-purple)] px-4 py-2 text-xs font-semibold uppercase tracking-wide text-white transition hover:brightness-110 disabled:opacity-60"
        >
          {isRegister ? "Create account" : "Sign in"}
        </button>
      </form>
    </main>
  );
};
