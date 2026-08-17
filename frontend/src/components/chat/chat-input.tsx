"use client";

import { useEffect, useRef, useState } from "react";
import { SendHorizonal } from "lucide-react";

type Props = {
  onSend: (message: string) => void;
  disabled?: boolean;
};

export default function ChatInput({ onSend, disabled = false }: Props) {
  const [value, setValue] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const canSend = value.trim().length > 0 && !disabled;

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
              disabled={disabled}
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

          <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-400">
            <span>Press Enter to send</span>
            <span>Shift + Enter for new line</span>
          </div>
        </div>
      </div>
    </div>
  );
}