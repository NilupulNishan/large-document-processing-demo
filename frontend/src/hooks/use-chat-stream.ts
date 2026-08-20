"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { loadSession, streamChat, type StoredMessage } from "@/lib/api";
import { usePolledMessages } from "./use-polled-messages";
import type { Citation, Message, Source } from "@/types/chat";

/** One stored row as the UI's shape. Used on load and again while polling a handoff. */
function fromStored(stored: StoredMessage): Message {
  return {
    id: stored.id,
    role: stored.role,
    content: stored.content,
    source: (stored.source as Source) ?? undefined,
    citations: stored.citations ?? [],
    steps: [],
    escalation: stored.escalation_id
      ? { id: stored.escalation_id, reason: stored.escalation_reason ?? "", pages: [] }
      : undefined,
  };
}

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
  // Once a person has the conversation the pipeline no longer answers, so the transcript is
  // mirrored from the server instead of streamed (D24).
  const [handedOver, setHandedOver] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const polled = usePolledMessages(sessionId, handedOver);
  const polledMessages = polled.messages;

  // Reopening a conversation restores it from the server, citations included.
  useEffect(() => {
    if (!sessionId) return;

    let ignore = false;
    loadSession(sessionId)
      .then((session) => {
        if (ignore) return;
        setMessages(session.messages.map(fromStored));
        // The server's live answer, not a guess from the transcript: an escalation_id is
        // permanent, so deriving it from the messages meant a closed handoff still read as
        // open forever.
        setHandedOver(session.handed_over);
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
      const startedAt = Date.now();
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
          } else if (frame.event === "handover") {
            // No assistant turn is coming; drop the placeholder that was added for one.
            setMessages((previous) => previous.slice(0, -1));
            setHandedOver(true);
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
        patchLast((message) => ({
          ...message,
          streaming: false,
          elapsedMs: Date.now() - startedAt,
        }));
        setBusy(false);
        abortRef.current = null;
      }
    },
    [sessionId, busy, patchLast],
  );

  /** Stops reading the stream and finalises the part-written answer. The server-side
   *  pipeline is not cancelled; only this client stops listening to it. */
  const stop = useCallback(() => abortRef.current?.abort(), []);

  // An agent closing the handoff returns the conversation to the pipeline. Adopt what
  // polling collected before letting go of it, or every agent turn would vanish the
  // moment the screen stopped reading from the poll.
  //
  // Adjusted during render rather than in an effect, as pdf-toolbar and the escalation
  // package do. It settles on the next render because handedOver is what gates it.
  if (handedOver && !polled.handedOver) {
    if (polledMessages.length > 0) setMessages(polledMessages.map(fromStored));
    setHandedOver(false);
  }

  // While a person has it, the server is the truth: their replies arrive by polling, and
  // nothing here is streaming.
  const shown = useMemo(
    () => (handedOver && polledMessages.length > 0 ? polledMessages.map(fromStored) : messages),
    [handedOver, polledMessages, messages],
  );

  // Derived, not reset in an effect: with no session there is nothing to show.
  return { messages: sessionId ? shown : [], send, stop, busy, handedOver };
}
