"use client";

import { FileText } from "lucide-react";
import ChatInput from "./chat-input";
import MessageList from "./message-list";
import type { Message } from "@/types/chat";

type Props = {
  /** The manual, used only until a conversation has a name of its own. */
  manualTitle?: string;
  /** What this conversation is about. The header names it; the global bar names the
   *  manual, so neither repeats the other. */
  conversationTitle?: string;
  messages: Message[];
  busy: boolean;
  ready: boolean;
  /** A person owns the conversation, so the composer says so rather than pretending (D24). */
  handedOver?: boolean;
  onSend: (text: string) => void;
  onStop?: () => void;
  onPageClick?: (pagePdf: number) => void;
};

export default function ChatPanel({
  manualTitle,
  conversationTitle,
  messages,
  busy,
  ready,
  handedOver = false,
  onSend,
  onStop,
  onPageClick,
}: Props) {
  // A session is called "New conversation" until the first question renames it, which is
  // a worse heading than the manual it is scoped to.
  const named =
    conversationTitle && conversationTitle !== "New conversation" ? conversationTitle : null;

  return (
    <div className="flex h-full flex-col overflow-hidden bg-surface">
      <div className="border-b border-divider px-6 py-3.5">
        <h2 className="truncate text-sm font-bold text-ink">
          {named || manualTitle || "Select a manual"}
        </h2>
        <p className="text-small text-ink-3">
          Answers cite the page they came from
        </p>
      </div>

      <div className="min-h-0 flex-1 overflow-hidden">
        {messages.length === 0 ? (
          <div className="flex h-full items-center justify-center px-8">
            <div className="max-w-sm text-center">
              <FileText className="mx-auto mb-3 h-7 w-7 text-ink-4" strokeWidth={1.4} />
              <p className="text-sm font-bold text-ink">
                Answers come with the page they came from
              </p>
              <p className="mt-1.5 text-body text-ink-2">
                Ask about a procedure, a warning light or a specification. Every answer says
                whether it came from your manual, and clicking a page opens it alongside.
              </p>
            </div>
          </div>
        ) : (
          <MessageList messages={messages} onPageClick={onPageClick} />
        )}
      </div>

      {/* ChatInput brings its own top border and padding. */}
      <ChatInput
        onSend={onSend}
        onStop={onStop}
        ready={ready}
        busy={busy}
        handedOver={handedOver}
      />
    </div>
  );
}
