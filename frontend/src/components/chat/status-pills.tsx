"use client";

type Props = {
  steps: string[];
  active: boolean;
};

/**
 * Each label is work the backend actually did. Nothing here is invented, and no
 * step appears that did not run (D9) — a confidently answered question shows no
 * grader step because no grader ran.
 */
export default function StatusPills({ steps, active }: Props) {
  if (steps.length === 0) return null;

  const latest = steps.length - 1;

  return (
    <div className="flex flex-col gap-1.5">
      {steps.map((label, index) => (
        <div
          key={`${index}-${label}`}
          className={`inline-flex items-center gap-2 text-xs ${
            active && index === latest ? "text-blue-700" : "text-slate-400"
          }`}
        >
          <span
            className={`h-1.5 w-1.5 shrink-0 rounded-full ${
              active && index === latest
                ? "animate-pulse bg-blue-600"
                : "bg-slate-300"
            }`}
          />
          <span>{label}</span>
        </div>
      ))}
    </div>
  );
}
