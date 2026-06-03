import {
  type DependencyList,
  startTransition,
  useEffect,
  useEffectEvent,
  useState,
} from "react";

interface AsyncResourceOptions<T> {
  enabled?: boolean;
  pollMs?: number;
  initialData?: T;
}

export function useAsyncResource<T>(
  loader: () => Promise<T>,
  deps: DependencyList,
  options: AsyncResourceOptions<T> = {},
) {
  const { enabled = true, pollMs, initialData } = options;
  const [data, setData] = useState<T | undefined>(initialData);
  const [error, setError] = useState<Error | undefined>();
  const [loading, setLoading] = useState(enabled);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshNonce, setRefreshNonce] = useState(0);

  const loadEvent = useEffectEvent(async (reason: "initial" | "refresh" | "poll") => {
    if (!enabled) {
      return;
    }
    if (reason === "initial") {
      setLoading(true);
    } else {
      setRefreshing(true);
    }
    setError(undefined);
    try {
      const nextData = await loader();
      startTransition(() => {
        setData(nextData);
      });
    } catch (value) {
      setError(
        value instanceof Error ? value : new Error("Unknown async resource error"),
      );
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }

    const initialTimer = window.setTimeout(() => {
      void loadEvent("initial");
    }, 0);
    if (!pollMs) {
      return () => window.clearTimeout(initialTimer);
    }

    const timer = window.setInterval(() => {
      void loadEvent("poll");
    }, pollMs);
    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, pollMs, refreshNonce, ...deps]);

  return {
    data,
    error,
    loading: enabled ? loading : false,
    refreshing,
    refresh: async () => {
      setRefreshNonce((value) => value + 1);
    },
  };
}
