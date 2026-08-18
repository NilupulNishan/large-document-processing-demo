/** The backend boundary. Wire formats stop here; components never call fetch. */

import { API_BASE } from "./config";
import type { Citation, Manual, SessionSummary, StreamEvent } from "@/types/chat";

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json();
}

export const listManuals = () => get<Manual[]>("/manuals");
export const listSessions = () => get<SessionSummary[]>("/sessions");
export const createSession = (manual: string) =>
  post<SessionSummary>("/sessions", { manual });

export type StoredMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  source: string | null;
  citations: Citation[];
  escalation_id: string | null;
  escalation_reason: string | null;
};

export const loadSession = (id: string) =>
  get<SessionSummary & { messages: StoredMessage[] }>(`/sessions/${id}`);

export const pdfUrl = (manualId: string) =>
  `${API_BASE}/manuals/${manualId}/pdf`;

/**
 * Stream one answer. Yields typed frames as they arrive rather than buffering,
 * which is the whole point of the transport (D9).
 */
export async function* streamChat(
  sessionId: string,
  question: string,
  signal?: AbortSignal,
): AsyncGenerator<StreamEvent> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, question }),
    signal,
  });

  if (!response.ok || !response.body) {
    throw new Error(`/chat returned ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });

    // Frames are separated by a blank line; a partial one stays in the buffer.
    let split = buffer.indexOf("\n\n");
    while (split !== -1) {
      const frame = buffer.slice(0, split);
      buffer = buffer.slice(split + 2);
      const parsed = parseFrame(frame);
      if (parsed) yield parsed;
      split = buffer.indexOf("\n\n");
    }
  }
}

function parseFrame(frame: string): StreamEvent | null {
  let event = "";
  let data = "";

  for (const line of frame.split("\n")) {
    if (line.startsWith("event: ")) event = line.slice(7);
    else if (line.startsWith("data: ")) data = line.slice(6);
  }

  if (!event || !data) return null;
  try {
    return { event, data: JSON.parse(data) } as StreamEvent;
  } catch {
    return null;
  }
}
