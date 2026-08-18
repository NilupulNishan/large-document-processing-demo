"use client";

import { CircleDot, CircleCheck, CircleDashed } from "lucide-react";
import type { EscalationSummary } from "@/types/chat";

type Props = {
  items: EscalationSummary[];
  selected: string | null;
  onSelect: (id: string) => void;
};

/** Read-only. Status is shown, never changed here — the endpoint exists, the screen does not use it. */
const STATUS = {
  open: { label: "Open", icon: CircleDot, className: "text-amber-600" },
  picked_up: { label: "Picked up", icon: CircleDashed, className: "text-sky-600" },
  closed: { label: "Closed", icon: CircleCheck, className: "text-slate-400" },
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
      <div className="rounded-xl border border-dashed border-slate-200 p-6 text-sm text-slate-500">
        <p className="font-medium text-slate-700">No handoffs yet.</p>
        <p className="mt-2 leading-6">
          A question reaches this screen when the gate will not answer it — ask the X55 what
          torque to tighten the wheel nuts to, and it will appear here with its reference.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {items.map((item) => {
        const status = STATUS[item.status] ?? STATUS.open;
        const Icon = status.icon;
        const active = item.id === selected;
        return (
          <button
            key={item.id}
            onClick={() => onSelect(item.id)}
            className={`w-full rounded-xl border p-3 text-left transition ${
              active
                ? "border-indigo-200 bg-indigo-50/60 shadow-sm"
                : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50"
            }`}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="font-mono text-xs font-semibold text-slate-900">{item.id}</span>
              <span className={`flex items-center gap-1 text-[11px] font-medium ${status.className}`}>
                <Icon className="h-3.5 w-3.5" />
                {status.label}
              </span>
            </div>
            <p className="mt-1.5 line-clamp-2 text-sm text-slate-700">{item.question}</p>
            <p className="mt-1.5 line-clamp-1 text-[11px] text-slate-500">{item.reason}</p>
            <p className="mt-1 text-[11px] text-slate-400">{ago(item.created_at)}</p>
          </button>
        );
      })}
    </div>
  );
}
