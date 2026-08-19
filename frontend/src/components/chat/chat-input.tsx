"use client";

import { useEffect, useRef, useState } from "react";
import { Loader2, Mic, Square, SendHorizonal } from "lucide-react";

import { useDictation } from "@/hooks/use-dictation";

type Props = {
  onSend: (message: string) => void;
  disabled?: boolean;
};

export default function ChatInput({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const appendDictated = (text: string) =>
    setValue((current) => (current ? `${current.trimEnd()} ${text}` : text));
  const dictation = useDictation(appendDictated);

  const busy = disabled || dictation.state === "transcribing";
  const canSend = value.trim().length > 0 && !busy;

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
    if (!message || disabled) return;

    onSend(message);
    setValue("");

    requestAnimationFrame(() => {
      if (textareaRef.current) {
        textareaRef.current.style.height = "44px";
      }
    });
  };

  return (
    <div className="border-t border-slate-200 bg-white px-4 py-4">
      <div className="mx-auto w-full">
        <div className="rounded-3xl border border-slate-200 bg-white shadow-sm transition-all focus-within:border-blue-300 focus-within:shadow-md">
          <div className="flex items-end gap-3 px-3 py-3">
            <textarea
              ref={textareaRef}
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="Ask a question, or describe the fault…"
              rows={1}
              disabled={busy}
              className="max-h-40 min-h-11 flex-1 resize-none bg-transparent px-2 py-2 text-[15px] leading-6 text-slate-800 outline-none placeholder:text-slate-400 disabled:cursor-not-allowed disabled:opacity-60"
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  handleSend();
                }
              }}
            />

            <button
              type="button"
              onClick={dictation.state === "listening" ? dictation.stop : dictation.start}
              disabled={disabled || dictation.state === "transcribing"}
              className={`flex h-11 w-11 items-center justify-center rounded-2xl transition-all duration-200 active:scale-95 ${
                dictation.state === "listening"
                  ? "bg-red-600 text-white shadow-sm hover:bg-red-700"
                  : "bg-slate-100 text-slate-500 hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
              }`}
              aria-label={dictation.state === "listening" ? "Stop recording" : "Dictate a question"}
            >
              {dictation.state === "transcribing" ? (
                <Loader2 size={18} className="animate-spin" />
              ) : dictation.state === "listening" ? (
                <Square size={16} />
              ) : (
                <Mic size={18} />
              )}
            </button>

            <button
              type="button"
              onClick={handleSend}
              disabled={!canSend}
              className={`flex h-11 w-11 items-center justify-center rounded-2xl transition-all duration-200 active:scale-95 ${
                canSend
                  ? "bg-blue-600 text-white shadow-sm hover:bg-blue-700"
                  : "cursor-not-allowed bg-slate-100 text-slate-400"
              }`}
              aria-label="Send message"
            >
              <SendHorizonal size={18} />
            </button>
          </div>

          {dictation.interim && (
            <p className="px-5 pb-2 text-[15px] leading-6 text-slate-400 italic">
              {dictation.interim}
            </p>
          )}

          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
            <span>
              {dictation.error
                ? dictation.error
                : dictation.state === "listening"
                  ? "Listening — press stop when you are done"
                  : dictation.state === "transcribing"
                    ? "Writing it down…"
                    : "Press Enter to send"}
            </span>
            <span>Shift + Enter for new line</span>
          </div>
        </div>
      </div>
    </div>
  );
}