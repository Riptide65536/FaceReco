import { useEffect, useEffectEvent, useState } from "react";

import { api } from "../lib/api/client";
import type { StreamFrame, UiEvent } from "../lib/api/types";

export function useEventFeed(limit = 8) {
  const [events, setEvents] = useState<UiEvent[]>([]);
  const [error, setError] = useState<Error | undefined>();

  const handleMessage = useEffectEvent((event: UiEvent) => {
    setEvents((current) => [event, ...current].slice(0, limit));
  });

  const handleError = useEffectEvent((value: Error) => {
    setError(value);
  });

  useEffect(() => {
    const unsubscribe = api.connectEvents(handleMessage, handleError);
    return unsubscribe;
  }, [limit]);

  return { events, error };
}

export function useStreamPreview(cameraId: string, enabled = true) {
  const [frame, setFrame] = useState<StreamFrame | undefined>();
  const [error, setError] = useState<Error | undefined>();

  const handleMessage = useEffectEvent((nextFrame: StreamFrame) => {
    setFrame(nextFrame);
  });

  const handleError = useEffectEvent((value: Error) => {
    setError(value);
  });

  useEffect(() => {
    if (!enabled) {
      return;
    }
    const unsubscribe = api.connectStream(cameraId, handleMessage, handleError);
    return unsubscribe;
  }, [cameraId, enabled]);

  return { frame, error };
}
