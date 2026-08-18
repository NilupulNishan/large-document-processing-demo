"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { loadSession, streamChat } from "@/lib/api";
import type { Citation, Message, Source } from "@/types/chat";

function blank(role: Message["role"], content = ""): Message {
  return {
    id: crypto.randomUUID(),
    role,
    content,
    citations: [],
    steps: [],
    streaming: role === "assistant",
  };
}

/** Owns the conversation. Messages persist server-side; this mirrors them. */
export function useChatStream(sessionId: string | null) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Reopening a conversation restores it from the server, citations included.
  useEffect(() => {
    if (!sessionId) return;

    let ignore = false;
    loadSession(sessionId)
      .then((session) => {
        if (ignore) return;
        setMessages(
          session.messages.map((stored) => ({
            id: stored.id,
            role: stored.role,
            content: stored.content,
            source: (stored.source as Source) ?? undefined,
            citations: stored.citations ?? [],
            steps: [],
            escalation: stored.escalation_id
              ? {
                  id: stored.escalation_id,
                  reason: stored.escalation_reason ?? "",
                  pages: [],
                }
              : undefined,
          })),
        );
      })
      .catch(() => {
        if (!ignore) setMessages([]);
      });

    return () => {
      ignore = true;
    };
  }, [sessionId]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const patchLast = useCallback((change: (message: Message) => Message) => {
    setMessages((previous) => {
      if (previous.length === 0) return previous;
      const next = [...previous];
      next[next.length - 1] = change(next[next.length - 1]);
      return next;
    });
  }, []);

  const send = useCallback(
    async (question: string) => {
      if (!sessionId || busy) return;

      setBusy(true);
      setMessages((previous) => [
        ...previous,
        blank("user", question),
        blank("assistant"),
      ]);

      const controller = new AbortController();
      abortRef.current = controller;

      try {
        for await (const frame of streamChat(sessionId, question, controller.signal)) {
          if (frame.event === "step") {
            const { label } = frame.data;
            patchLast((message) => ({ ...message, steps: [...message.steps, label] }));
          } else if (frame.event === "token") {
            const { text } = frame.data;
            patchLast((message) => ({ ...message, content: message.content + text }));
          } else if (frame.event === "done") {
            const { source, citations } = frame.data;
            patchLast((message) => ({
              ...message,
              source,
              citations: (citations ?? []) as Citation[],
              streaming: false,
            }));
          } else if (frame.event === "escalated") {
            const { message: text, ...escalation } = frame.data;
            patchLast((message) => ({
              ...message,
              content: message.content || text,
              escalation,
              streaming: false,
            }));
          } else if (frame.event === "error") {
            const { message: text } = frame.data;
            patchLast((message) => ({
              ...message,
              content: message.content || text,
              streaming: false,
              failed: true,
            }));
          }
          // An unknown event is ignored, not treated as a failure. Matching `error` by
          // elimination is how `escalated` first rendered as a crash.
        }
      } catch {
        patchLast((message) => ({
          ...message,
          content: message.content || "The connection dropped before the answer finished.",
          streaming: false,
          failed: true,
        }));
      } finally {
        // A stream that ends without `done` must not leave the caret spinning.
        patchLast((message) => ({ ...message, streaming: false }));
        setBusy(false);
        abortRef.current = null;
      }
    },
    [sessionId, busy, patchLast],
  );

  // Derived, not reset in an effect: with no session there is nothing to show.
  return { messages: sessionId ? messages : [], send, busy };
}
