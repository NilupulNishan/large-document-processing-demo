/**
 * Mirrors the backend contract. A change to Answer or the SSE events in
 * backend/app/pipeline/base.py should fail the type check here.
 */

/** Page and web are separate types so the UI cannot render them alike (D13). */
export type Citation =
  | {
      type: "page";
      page_pdf: number;
      page_printed?: number | null;
      section?: string | null;
    }
  | { type: "web"; url: string; title?: string | null };

export type Source = "manual" | "manual+general" | "general";

export type AnswerFormat = "direct" | "steps" | "troubleshoot" | "explanation";

export type Manual = {
  id: string;
  title: string;
  filename: string;
  page_count: number;
  page_offset: number | null;
};

export type SessionSummary = {
  id: string;
  manual_id: string;
  title: string;
  messages: number;
  updated_at: string;
};

/** A handed-over question. Carries no source and no citations: it is not an answer (D12). */
export type Escalation = {
  id: string;
  reason: string;
  pages: number[];
  status?: "open" | "picked_up" | "closed";
  created_at?: string;
};

/** A row in the operator inbox. Mirrors db.list_escalations. */
export type EscalationSummary = Escalation & {
  session_id: string;
  manual_id: string;
  question: string;
  /** D14's written payload. Null on records created before Slice 16. */
  summary: string | null;
  next_step: string | null;
  status: "open" | "picked_up" | "closed";
  created_at: string;
  updated_at: string;
};

/** One SSE frame. `step` labels describe work that actually ran (D9). */
export type StreamEvent =
  | { event: "step"; data: { step: string; label: string } }
  | { event: "token"; data: { text: string } }
  | {
      event: "done";
      data: {
        source: Source;
        format: AnswerFormat;
        answer: string;
        citations?: Citation[];
        resolved: boolean;
      };
    }
  | { event: "escalated"; data: Escalation & { message: string } }
  | { event: "handover"; data: { escalation_id: string } }
  | { event: "error"; data: { message: string } };

export type Message = {
  id: string;
  /** `agent` is a human replying after a handoff — never the pipeline (D24). */
  role: "user" | "assistant" | "agent";
  content: string;
  /** Absent until the stream finishes; drives the source badge. */
  source?: Source;
  citations: Citation[];
  steps: string[];
  streaming?: boolean;
  failed?: boolean;
  /** Set instead of `source` when the question was handed to a person. */
  escalation?: Escalation;
};
