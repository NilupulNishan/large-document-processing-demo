"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowDown } from "lucide-react";
import MessageItem from "./message-item";
import type { Message } from "@/types/chat";

type Props = {
  messages: Message[];
  onPageClick?: (pagePdf: number) => void;
};

/** Close enough to the bottom that the reader still means to be following. */
const NEAR_BOTTOM = 80;

export default function MessageList({ messages, onPageClick }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const countRef = useRef(messages.length);
  const [atBottom, setAtBottom] = useState(true);

  const scrollToBottom = useCallback((behavior: ScrollBehavior) => {
    bottomRef.current?.scrollIntoView({ behavior, block: "end" });
  }, []);

  // Set only when the answer changes: a scroll listener that calls setState on every
  // event would re-render the whole transcript while tokens are arriving.
  const handleScroll = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;
    const near =
      container.scrollHeight - container.scrollTop - container.clientHeight < NEAR_BOTTOM;
    setAtBottom((previous) => (previous === near ? previous : near));
  }, []);

  useEffect(() => {
    const grew = messages.length > countRef.current;
    countRef.current = messages.length;

    // Sending is an explicit request to be at the bottom, so it re-pins even if the
    // reader had scrolled away.
    if (grew) {
      setAtBottom(true);
      scrollToBottom("smooth");
      return;
    }

    // Tokens: follow only while the reader is still at the bottom, and jump rather than
    // animate — a smooth scroll retriggered every few milliseconds fights itself.
    if (atBottom) scrollToBottom("auto");
  }, [messages, atBottom, scrollToBottom]);

  const streaming = messages[messages.length - 1]?.streaming;

  return (
    <div className="relative h-full">
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="h-full overflow-y-auto px-6 py-5"
      >
        <div className="flex flex-col gap-5">
          {messages.map((message) => (
            <MessageItem
              key={message.id}
              message={message}
              onPageClick={onPageClick}
            />
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      {/* Freeing the reader must not hide that an answer is still arriving. */}
      {!atBottom && streaming && (
        <button
          onClick={() => {
            setAtBottom(true);
            scrollToBottom("smooth");
          }}
          className="animate-enter absolute bottom-4 left-1/2 flex h-8 -translate-x-1/2 items-center gap-1.5 rounded-full border border-line bg-surface px-3 text-small font-semibold text-ink shadow-sm hover:bg-raised"
        >
          <ArrowDown className="h-3.5 w-3.5" strokeWidth={2} />
          Jump to latest
        </button>
      )}
    </div>
  );
}
