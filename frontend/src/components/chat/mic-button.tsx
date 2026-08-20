"use client";

import { Loader2, Mic, Square } from "lucide-react";
import type { DictationState } from "@/hooks/use-dictation";

type Props = {
  state: DictationState;
  onStart: () => void;
  onStop: () => void;
  disabled?: boolean;
};

/**
 * Presentation only — `useDictation` owns the state. Shared by the customer's composer and
 * the agent's reply box so the two cannot drift: starting is slow enough to need a spinner
 * (a token fetch, a 7 MB import and a socket), and a mic that looks idle while it opens is
 * what made people click twice and dictate everything into the box twice (D39).
 */
export default function MicButton({ state, onStart, onStop, disabled = false }: Props) {
  const listening = state === "listening";
  const busy = state === "starting" || state === "transcribing";

  return (
    <button
      type="button"
      onClick={listening ? onStop : onStart}
      disabled={disabled || busy}
      aria-label={listening ? "Stop recording" : "Dictate"}
      className={`relative grid h-9 w-9 shrink-0 place-items-center rounded transition-colors active:scale-95 ${
        listening
          ? "bg-danger text-white"
          : "border border-line text-ink-2 hover:bg-raised disabled:text-ink-4"
      }`}
    >
      {listening && (
        <span
          aria-hidden
          className="animate-live absolute inset-0 rounded border-2 border-danger"
        />
      )}
      {busy ? (
        <Loader2 className="h-4 w-4 animate-spin" />
      ) : listening ? (
        <Square className="h-3.5 w-3.5" fill="currentColor" />
      ) : (
        <Mic className="h-4 w-4" strokeWidth={1.7} />
      )}
    </button>
  );
}
