"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizonal, Square, UserRound } from "lucide-react";

import MicButton from "./mic-button";
import { useDictation } from "@/hooks/use-dictation";

type Props = {
  onSend: (message: string) => void;
  onStop?: () => void;
  /** A manual is chosen and a session exists. */
  ready?: boolean;
  /** The assistant is answering. Kept separate from `ready`: they are different states. */
  busy?: boolean;
  /** A person owns the conversation, so the pipeline writes nothing (D24). */
  handedOver?: boolean;
};

export default function ChatInput({
  onSend,
  onStop,
  ready = false,
  busy = false,
  handedOver = false,
}: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const appendDictated = (text: string) =>
    setValue((current) => (current ? `${current.trimEnd()} ${text}` : text));
  const dictation = useDictation(appendDictated);

  const starting = dictation.state === "starting";
  const listening = dictation.state === "listening";
  const transcribing = dictation.state === "transcribing";
  const typed = value.trim().length > 0;

  // First match wins. The control and the line below it are read from this one value, so
  // they cannot tell the user two different things.
  const status = handedOver
    ? { hint: "A specialist has this conversation. Your reply goes to them.", tone: "person" }
    : !ready
      ? { hint: "Choose a manual to begin", tone: "quiet" }
      : busy
        ? { hint: "Answering, press stop to end it", tone: "quiet" }
        : starting
          ? { hint: "Opening the microphone", tone: "quiet" }
          : transcribing
            ? { hint: "Writing it down", tone: "quiet" }
            : listening && dictation.mode === "recording"
              ? { hint: "Live transcription unavailable, recording instead", tone: "warn" }
              : listening
                ? { hint: "Listening, press stop when you are done", tone: "quiet" }
                : dictation.error
                  ? { hint: dictation.error, tone: "warn" }
                  : { hint: "Enter to send, Shift + Enter for a new line", tone: "quiet" };

  const locked = !ready || busy || transcribing;
  // A guess still being revised is not a sentence anyone meant to send.
  const canSend = typed && !locked && !listening && !starting && !dictation.interim;

  const resizeTextarea = () => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  };

  useEffect(() => {
    resizeTextarea();
  }, [value]);

  const handleSend = () => {
    const message = value.trim();
    if (!message || locked) return;

    onSend(message);
    setValue("");

    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "36px";
      }
    });
  };

  return (
    <div className="border-t border-divider px-6 pb-5 pt-4">
      <div
        className={`rounded-lg border bg-surface transition-colors focus-within:border-action ${
          listening ? "border-action" : handedOver ? "border-person-line" : "border-line"
        }`}
      >
        <div className="flex items-end gap-2.5 p-2.5 pl-3.5">
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="Ask a question, or describe the fault"
            rows={1}
            disabled={locked}
            className="max-h-40 min-h-9 flex-1 resize-none bg-transparent py-2 text-body leading-5 text-ink outline-none placeholder:text-ink-3 disabled:text-ink-3"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
          />

          <MicButton
            state={dictation.state}
            onStart={dictation.start}
            onStop={dictation.stop}
            disabled={!ready || busy}
          />

          {/* While answering, the same slot stops the answer. Saying "stop" and not stopping
              would be worse than not offering it. */}
          {busy ? (
            <button
              type="button"
              onClick={onStop}
              className="grid h-9 w-9 shrink-0 place-items-center rounded border border-line text-ink-2 transition-colors hover:bg-raised active:scale-95"
              aria-label="Stop answering"
            >
              <Square className="h-3.5 w-3.5" fill="currentColor" />
            </button>
          ) : (
            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className={`grid h-9 w-9 shrink-0 place-items-center rounded transition-colors active:scale-95 ${
                canSend ? "bg-action text-white hover:bg-action-hover" : "bg-divider text-ink-4"
              }`}
              aria-label="Send message"
            >
              <SendHorizonal className="h-4 w-4" strokeWidth={1.8} />
            </button>
          )}
        </div>

        {/* The guess is visibly unsettled until the recogniser commits it. */}
        {dictation.interim && (
          <p className="animate-breathe px-3.5 pb-2.5 text-body leading-5 text-ink-2">
            {dictation.interim}
          </p>
        )}
      </div>

      <p
        className={`mt-2 flex items-center gap-1.5 px-0.5 text-small ${
          status.tone === "warn"
            ? "text-general"
            : status.tone === "person"
              ? "text-person"
              : "text-ink-3"
        }`}
      >
        {status.tone === "person" && <UserRound className="h-3.5 w-3.5" strokeWidth={1.8} />}
        {status.hint}
      </p>
    </div>
  );
}
