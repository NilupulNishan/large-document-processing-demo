"use client";

import { useEffect, useState } from "react";
import { loadSession, type StoredMessage } from "@/lib/api";

/**
 * Mirrors one session's messages while a human has the conversation.
 *
 * Polling rather than a persistent stream (D24): the existing SSE is request-scoped and ends
 * with the answer, and a long-lived channel would need a subscriber registry, disconnect
 * detection and reconnect — all of which is lost on a dev-server reload. Two seconds is well
 * inside the time a person takes to type.
 */
export function usePolledMessages(sessionId: string | null, active: boolean, everyMs = 2000) {
  const [messages, setMessages] = useState<StoredMessage[]>([]);

  useEffect(() => {
    if (!sessionId || !active) return;

    let stopped = false;
    const pull = () =>
      loadSession(sessionId)
        .then((session) => !stopped && setMessages(session.messages))
        .catch(() => undefined);

    pull();
    const timer = setInterval(pull, everyMs);
    return () => {
      stopped = true;
      clearInterval(timer);
    };
  }, [sessionId, active, everyMs]);

  return messages;
}
