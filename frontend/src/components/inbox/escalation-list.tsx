"use client";

import type { EscalationSummary } from "@/types/chat";

type Props = {
  items: EscalationSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
};

/** Status is a queue position, so it reads as a colour with a shape, never colour alone. */
const STATUS = {
  open: { label: "Open", className: "border-general-line bg-general-soft text-general" },
  picked_up: { label: "Picked up", className: "border-manual-line bg-manual-soft text-manual" },
  closed: { label: "Closed", className: "border-divider bg-raised text-ink-3" },
} as const;

function ago(iso: string) {
  const seconds = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

export default function EscalationList({ items, selected, onSelect }: Props) {
  if (items.length === 0) {
    return (
      <div className="rounded border border-dashed border-line p-5 text-body text-ink-2">
        <p className="font-semibold text-ink">No handoffs yet.</p>
        <p className="mt-2 leading-5">
          A question reaches this screen when the gate will not answer it — ask the X55 what
          torque to tighten the wheel nuts to, and it will appear here with its reference.
        </p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-1.5">
      {items.map((item) => {
        const status = STATUS[item.status] ?? STATUS.open;
        const active = item.id === selected;
        const waiting = item.status === "open";
        return (
          <button
            key={item.id}
            onClick={() => onSelect(item.id)}
            aria-current={active ? "true" : undefined}
            className={`rounded border-l-2 p-3 text-left transition-colors ${
              active
                ? "border-l-person bg-person-soft/50"
                : "border-l-transparent hover:bg-raised"
            }`}
          >
            <div className="flex items-center gap-2">
              {/* A live pulse only where something is actually waiting on a person. */}
              <span className="relative grid h-2 w-2 shrink-0 place-items-center">
                {waiting && (
                  <span className="animate-live absolute inset-0 rounded-full bg-person" />
                )}
                <span
                  className={`h-2 w-2 rounded-full ${waiting ? "bg-person" : "bg-ink-4"}`}
                />
              </span>
              <span className="font-mono text-small font-semibold text-ink-2">{item.id}</span>
              <span className="ml-auto text-small text-ink-3">{ago(item.created_at)}</span>
            </div>

            <p className="mt-1.5 line-clamp-2 text-body font-semibold text-ink">
              {item.question}
            </p>
            <p className="mt-1 line-clamp-1 text-small text-ink-2">{item.reason}</p>

            <span
              className={`mt-2 inline-block rounded border px-1.5 py-0.5 text-small font-semibold ${status.className}`}
            >
              {status.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}
