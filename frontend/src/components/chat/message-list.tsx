"use client";

import { useEffect, useRef } from "react";
import MessageItem from "./message-item";
import type { Message } from "@/types/chat";

type Props = {
  messages: Message[];
  onPageClick?: (pagePdf: number) => void;
};

export default function MessageList({ messages, onPageClick }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    bottomRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "end",
    });
  }, [messages]);

  return (
    <div
      ref={containerRef}
      className="h-full overflow-y-auto px-4 py-4"
    >
      <div className="space-y-4">
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
  );
}