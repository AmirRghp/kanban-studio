"use client";

import { useCallback, useEffect, useState } from "react";
import { Workspace } from "@/components/Workspace";
import { LoginView } from "@/components/LoginView";
import { fetchSession, signOut } from "@/lib/api";

type Status = "checking" | "signed-out" | "signed-in";

export const App = () => {
  const [status, setStatus] = useState<Status>("checking");
  const [username, setUsername] = useState("");

  useEffect(() => {
    let cancelled = false;

    fetchSession()
      .then((user) => {
        if (cancelled) return;
        if (user) {
          setUsername(user.username);
          setStatus("signed-in");
        } else {
          setStatus("signed-out");
        }
      })
      .catch(() => {
        if (!cancelled) setStatus("signed-out");
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const handleSignedIn = useCallback((name: string) => {
    setUsername(name);
    setStatus("signed-in");
  }, []);

  const handleSignOut = useCallback(async () => {
    await signOut();
    setUsername("");
    setStatus("signed-out");
  }, []);

  // A static export has no server to route, so there is no separate /login page. The
  // board must not render until the session check resolves, or it would flash for
  // signed-out visitors.
  if (status === "checking") {
    return (
      <main className="flex min-h-screen items-center justify-center">
        <p className="text-sm text-[var(--gray-text)]">Checking your session...</p>
      </main>
    );
  }

  if (status === "signed-out") {
    return <LoginView onSignedIn={handleSignedIn} />;
  }

  return <Workspace username={username} onSignOut={handleSignOut} />;
};
