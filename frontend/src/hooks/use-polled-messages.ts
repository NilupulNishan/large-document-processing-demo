"use client";

import { useEffect, useRef, useState } from "react";
import { loadSession, type StoredMessage } from "@/lib/api";

/** Cheap identity check: a transcript only ever grows, so length plus the last id is enough. */
function same(a: StoredMessage[], b: StoredMessage[]) {
  return a.length === b.length && a[a.length - 1]?.id === b[b.length - 1]?.id;
}

/**
 * Mirrors one session's messages while a human has the conversation.
 *
 * Polling rather than a persistent stream (D24): the existing SSE is request-scoped and ends
 * with the answer, and a long-lived channel would need a subscriber registry, disconnect
 * detection and reconnect — all lost on a dev-server reload.
 *
 * It backs off while nothing is happening and snaps back the moment a turn arrives, so an inbox
 * left open overnight is not asking the same question every two seconds forever.
 */
export function usePolledMessages(
  sessionId: string | null,
  active: boolean,
  everyMs = 2000,
  maxMs = 15000,
) {
  const [messages, setMessages] = useState<StoredMessage[]>([]);
  const lastRef = useRef<StoredMessage[]>([]);

  useEffect(() => {
    if (!sessionId || !active) return;

    let stopped = false;
    let delay = everyMs;
    let timer: ReturnType<typeof setTimeout>;

    const tick = async () => {
      if (stopped) return;
      // A hidden tab has nobody reading it. Skip the request, keep the schedule.
      if (typeof document !== "undefined" && document.hidden) {
        timer = setTimeout(tick, delay);
        return;
      }
      try {
        const session = await loadSession(sessionId);
        if (stopped) return;
        if (same(lastRef.current, session.messages)) {
          // Nothing said. Ease off rather than asking again immediately.
          delay = Math.min(delay * 2, maxMs);
        } else {
          lastRef.current = session.messages;
          setMessages(session.messages);
          delay = everyMs;
        }
      } catch {
        // A failed poll is not fatal; the next one may succeed.
      }
      if (!stopped) timer = setTimeout(tick, delay);
    };

    // Coming back to the tab should feel immediate, not up to `maxMs` stale.
    const wake = () => {
      if (stopped || document.hidden) return;
      delay = everyMs;
      clearTimeout(timer);
      timer = setTimeout(tick, 0);
    };

    tick();
    document.addEventListener("visibilitychange", wake);
    return () => {
      stopped = true;
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", wake);
    };
  }, [sessionId, active, everyMs, maxMs]);

  return messages;
}
