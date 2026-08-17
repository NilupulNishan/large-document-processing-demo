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
    <div className="flex h-full flex-col overflow-hidden rounded-2xl border border-slate-200 bg-slate-50">
      <div className="border-b border-slate-200 bg-white px-5 py-4">
        <h2 className="text-base font-semibold text-slate-800">
          {manualTitle || "Select a manual"}
        </h2>
        <p className="text-sm text-slate-500">
          Ask a question or describe a fault.
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center px-8 text-center">
            <p className="max-w-sm text-sm text-slate-400">
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
