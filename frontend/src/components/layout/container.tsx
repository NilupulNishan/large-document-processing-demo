"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Group, Panel, Separator } from "react-resizable-panels";
import AppHeader from "./app-header";
import Sidebar from "./sidebar";
import ChatPanel from "@/components/chat/chat-panel";
import PdfViewer from "@/components/pdf/pdf-viewer";
import { useChatStream } from "@/hooks/use-chat-stream";
import {
  createSession,
  deleteSession,
  listEscalations,
  listManuals,
  listSessions,
  pdfUrl,
} from "@/lib/api";
import type { Manual, SessionSummary } from "@/types/chat";

export default function AppShell() {
  const [manuals, setManuals] = useState<Manual[]>([]);
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [manualId, setManualId] = useState<string | null>(null);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [openHandoffs, setOpenHandoffs] = useState(0);

  const { messages, send, stop, busy, handedOver } = useChatStream(sessionId);

  const refreshSessions = useCallback(() => {
    listSessions().then(setSessions).catch(() => setSessions([]));
    // The badge counts real open handoffs. An invented number here would be the one
    // kind of fake this product cannot afford.
    listEscalations()
      .then((found) => setOpenHandoffs(found.filter((item) => item.status === "open").length))
      .catch(() => setOpenHandoffs(0));
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

  // Deleting the open conversation must land somewhere: the next most recent, or a fresh one
  // on the same manual when that was the last.
  const removeSession = useCallback(
    async (id: string) => {
      await deleteSession(id).catch(() => undefined);
      const remaining = await listSessions().catch(() => []);
      setSessions(remaining);

      if (id !== sessionId) return;
      const next = remaining.find((item) => item.id !== id);
      if (next) {
        setManualId(next.manual_id);
        setSessionId(next.id);
        setPage(1);
      } else if (manualId) {
        startSession(manualId);
      } else {
        setSessionId(null);
      }
    },
    [sessionId, manualId, startSession],
  );

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
    <div className="flex h-screen w-full flex-col overflow-hidden bg-ground">
      <AppHeader
        manuals={manuals}
        selectedManual={manualId}
        onSelectManual={selectManual}
        openHandoffs={openHandoffs}
      />

      <div className="flex min-h-0 flex-1 overflow-hidden bg-surface">
        <Sidebar
          manuals={manuals}
          sessions={history}
          selectedManual={manualId}
          selectedSession={sessionId}
          onSelectManual={selectManual}
          onSelectSession={selectSession}
          onDeleteSession={removeSession}
          onNewChat={() => manualId && startSession(manualId)}
        />

        <div className="min-h-0 min-w-0 flex-1 overflow-hidden">
          <Group orientation="horizontal" className="h-full min-h-0 min-w-0">
            <Panel defaultSize="55%" minSize="30%">
              <div className="h-full min-h-0 min-w-0 overflow-hidden">
                <ChatPanel
                  manualTitle={manual?.title}
                  conversationTitle={
                    sessions.find((item) => item.id === sessionId)?.title
                  }
                  messages={messages}
                  busy={busy}
                  ready={Boolean(sessionId)}
                  handedOver={handedOver}
                  onSend={send}
                  onStop={stop}
                  onPageClick={setPage}
                />
              </div>
            </Panel>

            <Separator className="group relative flex w-1.5 items-center justify-center bg-divider">
              <div className="h-full w-full bg-transparent transition-colors group-hover:bg-action" />
            </Separator>

            <Panel defaultSize="45%" minSize="30%">
              <div className="h-full min-h-0 min-w-0 overflow-hidden">
                <PdfViewer
                  // Remount on a new document rather than resetting page state
                  // in an effect.
                  key={manual?.id ?? "none"}
                  url={manual ? pdfUrl(manual.id) : undefined}
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
