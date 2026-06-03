/* eslint-disable react-refresh/only-export-components */
import {
  type PropsWithChildren,
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { api, setApiToken } from "../lib/api/client";
import type { AuthCredentials, AuthSession } from "../lib/api/types";

const SESSION_STORAGE_KEY = "task02.frontend.session";

interface SessionContextValue {
  isAuthenticated: boolean;
  session?: AuthSession;
  login: (credentials: AuthCredentials) => Promise<AuthSession>;
  logout: () => void;
}

const SessionContext = createContext<SessionContextValue | null>(null);

function readStoredSession(): AuthSession | undefined {
  const raw = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return undefined;
  }
  try {
    return JSON.parse(raw) as AuthSession;
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return undefined;
  }
}

export function SessionProvider({ children }: PropsWithChildren) {
  const [session, setSession] = useState<AuthSession | undefined>(() =>
    readStoredSession(),
  );

  useEffect(() => {
    setApiToken(session?.token ?? "");
  }, [session]);

  const value = useMemo<SessionContextValue>(
    () => ({
      isAuthenticated: Boolean(session?.token),
      session,
      async login(credentials) {
        const nextSession = await api.login(credentials);
        setSession(nextSession);
        window.localStorage.setItem(
          SESSION_STORAGE_KEY,
          JSON.stringify(nextSession),
        );
        setApiToken(nextSession.token);
        return nextSession;
      },
      logout() {
        setSession(undefined);
        setApiToken("");
        window.localStorage.removeItem(SESSION_STORAGE_KEY);
      },
    }),
    [session],
  );

  return (
    <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
  );
}

export function useSession() {
  const context = useContext(SessionContext);
  if (!context) {
    throw new Error("useSession must be used inside SessionProvider");
  }
  return context;
}
