"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import Sidebar from "./sidebar";
import ChatPanel from "@/components/chat/chat-panel";
import PdfViewer from "@/components/pdf/pdf-viewer";
import { useChatStream } from "@/hooks/use-chat-stream";
import { createSession, listManuals, listSessions, pdfUrl } from "@/lib/api";
import type { Manual, SessionSummary } from "@/types/chat";

export default function AppShell() {
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [manualId, setManualId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [page, setPage] = useState(1);

  const { messages, send, busy } = useChatStream(sessionId);

  const refreshSessions = useCallback(() => {
    listSessions().then(setSessions).catch(() => setSessions([]));
  }, []);

  // The opening session is created here rather than reactively: send() would
  // otherwise close over a null id and lose the first message of a conversation.
  useEffect(() => {
    listManuals()
      .then(async (found) => {
        setManuals(found);
        if (found.length === 0) return;
        setManualId(found[0].id);
        const session = await createSession(found[0].id);
        setSessionId(session.id);
      })
      .catch(() => setManuals([]));
    refreshSessions();
  }, [refreshSessions]);

  const manual = useMemo(
    () => manuals.find((item) => item.id === manualId) ?? null,
    [manuals, manualId],
  );

  const startSession = useCallback(
    async (forManual: string) => {
      const session = await createSession(forManual);
      setSessionId(session.id);
      setPage(1);
      refreshSessions();
    },
    [refreshSessions],
  );

  // A conversation is locked to one manual, so switching manuals starts a new
  // one rather than mixing two documents in one history (D11).
  const selectManual = (id: string) => {
    if (id === manualId) return;
    setManualId(id);
    setPage(1);
    startSession(id);
  };

  const selectSession = (id: string) => {
    const chosen = sessions.find((item) => item.id === id);
    if (!chosen) return;
    setManualId(chosen.manual_id);
    setSessionId(id);
    setPage(1);
  };

  useEffect(() => {
    if (!busy) refreshSessions();
  }, [busy, refreshSessions]);

  // An untouched session is a real row but not a conversation; showing it would
  // fill the history with "New conversation" every time a manual is picked.
  const history = useMemo(
    () => sessions.filter((item) => item.messages > 0 || item.id === sessionId),
    [sessions, sessionId],
  );

  return (
    <div className="h-screen w-full overflow-hidden bg-slate-100">
      <div className="flex h-full gap-4 overflow-hidden bg-white p-4">
        <Sidebar
          manuals={manuals}
          sessions={history}
          selectedManual={manualId}
          selectedSession={sessionId}
          onSelectManual={selectManual}
          onSelectSession={selectSession}
          onNewChat={() => manualId && startSession(manualId)}
        />

        <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Group orientation="horizontal" className="h-full min-h-0 min-w-0">
            <Panel defaultSize="55%" minSize="30%">
              <div className="h-full min-h-0 min-w-0 overflow-hidden pr-2">
                <ChatPanel
                  manualTitle={manual?.title}
                  messages={messages}
                  busy={busy}
                  ready={Boolean(sessionId)}
                  onSend={send}
                  onPageClick={setPage}
                />
              </div>
            </Panel>

            <Separator className="group relative mx-1 flex w-2 items-center justify-center">
              <div className="h-full w-1 rounded-full bg-slate-200 transition-colors group-hover:bg-blue-400" />
            </Separator>

            <Panel defaultSize="45%" minSize="30%">
              <div className="h-full min-h-0 min-w-0 overflow-hidden pl-2">
                <PdfViewer
                  // Remount on a new document rather than resetting page state
                  // in an effect.
                  key={manual?.id ?? "none"}
                  url={manual ? pdfUrl(manual.id) : undefined}
                  title={manual?.title}
                  subtitle={manual ? `${manual.page_count} pages` : undefined}
                  page={page}
                />
              </div>
            </Panel>
          </Group>
        </div>
      </div>
    </div>
  );
}
