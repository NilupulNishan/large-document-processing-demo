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
  | { event: "error"; data: { message: string } };

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  /** Absent until the stream finishes; drives the source badge. */
  source?: Source;
  citations: Citation[];
  steps: string[];
  streaming?: boolean;
  failed?: boolean;
};
