"use client";

import { Check } from "lucide-react";

type Props = {
  steps: string[];
  active: boolean;
};

/**
 * Each label is work the backend actually did. Nothing here is invented, and no
 * step appears that did not run (D9) — a confidently answered question shows no
 * grader step because no grader ran.
 *
 * The rail is the visible proof that a real pipeline ran, so it gets the room and the
 * motion. What it cannot do is imply progress it has not been told about: there is no
 * bar creeping toward a total, because nothing knows the total.
 */
export default function StatusPills({ steps, active }: Props) {
  if (steps.length === 0) return null;

  // While running, the last step is the one in flight; everything before it is done.
  const done = active ? steps.length - 1 : steps.length;

  return (
    <ol className="relative flex flex-col gap-3">
      {/* The line reaches the last finished step and no further. */}
      <span aria-hidden className="absolute left-[8px] top-2 bottom-2 w-0.5 bg-divider" />
      <span
        aria-hidden
        className="absolute left-[8px] top-2 w-0.5 bg-action transition-[height] duration-500 ease-out"
        style={{ height: `calc(${(done / Math.max(steps.length, 1)) * 100}% - 0.5rem)` }}
      />

      {steps.map((label, index) => {
        const complete = index < done;
        const running = active && index === steps.length - 1;

        return (
          <li
            key={`${index}-${label}`}
            className="animate-enter relative flex items-center gap-3"
            style={{ animationDelay: `${index * 60}ms` }}
          >
            <span className="relative z-10 grid h-[18px] w-[18px] shrink-0 place-items-center rounded-full bg-surface">
              {complete ? (
                <span className="grid h-[18px] w-[18px] place-items-center rounded-full border-[1.5px] border-person">
                  <Check className="animate-pop h-2.5 w-2.5 text-person" strokeWidth={3} />
                </span>
              ) : running ? (
                <>
                  <span className="animate-live absolute inset-0 rounded-full border-2 border-action" />
                  <span className="h-2 w-2 rounded-full bg-action" />
                </>
              ) : (
                <span className="h-2 w-2 rounded-full bg-ink-4" />
              )}
            </span>

            <span
              className={`text-body ${running ? "font-semibold text-ink" : "text-ink-2"}`}
            >
              {label}
            </span>
          </li>
        );
      })}
    </ol>
  );
}
