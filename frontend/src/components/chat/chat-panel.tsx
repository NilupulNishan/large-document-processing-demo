"use client";

import ChatInput from "./chat-input";
import MessageList from "./message-list";
import type { Message } from "@/types/chat";

type Props = {
  manualTitle?: string;
  messages: Message[];
  busy: boolean;
  ready: boolean;
  onSend: (text: string) => void;
  onPageClick?: (pagePdf: number) => void;
};

export default function ChatPanel({
  manualTitle,
  messages,
  busy,
  ready,
  onSend,
  onPageClick,
}: Props) {
  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <div className="border-b border-divider px-6 py-3.5">
        <h2 className="text-sm font-bold text-ink">
          {manualTitle || "Select a manual"}
        </h2>
        <p className="text-small text-ink-3">
          Ask a question or describe a fault.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center px-8 text-center">
            <p className="max-w-sm text-body text-ink-2">
              Answers come with the page they came from. Click a page to open it
              alongside.
            </p>
          </div>
        ) : (
          <MessageList messages={messages} onPageClick={onPageClick} />
        )}
      </div>

      {/* ChatInput brings its own top border and padding. */}
      <ChatInput onSend={onSend} disabled={!ready || busy} />
    </div>
  );
}
