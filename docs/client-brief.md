# Client brief

## The situation

A company maintains a library of product manuals and supports the people who use those products —
either its own customers, or the customers of the businesses it serves. Today, answering a question
means someone opening a 250-page PDF and hunting for the right section, or opening a support ticket.

Manuals are long, densely cross-referenced, and written for reference rather than reading. The
information is almost always in there. Finding it is the problem.

## User story

> As someone using a product I don't know well, I want to select my specific manual and describe my
> problem in plain language, so that I get a clear answer with the exact page shown next to it. When
> the manual does not cover my problem, I want the assistant to keep helping rather than give up —
> and to reach a person only when nothing else has worked, without having to repeat myself.

The assistant should feel like a technical expert sitting beside the user, not a search box over a PDF.

## Who this is for

The buyer is a company that processes manuals and provides guidance to its users. The end user is
that company's customer. So the product must look credible to the buyer *and* be usable by someone
who has never seen it before.

## What the build includes

**Manual selection**
1. The user picks one manual from the set already ingested. One manual per conversation.
2. Ingestion is an offline script. There is no in-app upload.

**Answering**
3. The answer format adapts to the question — a direct fact, a numbered procedure, a diagnostic
   sequence, or an explanation. It is not always step-by-step.
4. Every answer carries exact page citations. A citation may span two or three pages.
5. Answers reproduce the manual's safety warnings verbatim. They are never paraphrased away.

**Side-by-side view**
6. The answer sits beside a rendered view of the cited manual page.
7. Clicking a citation moves the viewer to that page.

**Sessions**
8. Each conversation has its own memory, persisted to SQLite.
9. The user can start a new conversation at any time.
10. A left panel lists previous conversations.
11. Selecting one reopens its full history.
12. A reopened conversation continues correctly — a follow-up question is understood in the context
    of what came before.
13. An unrelated question inside an old conversation is answered on its own merits. History is
    retained but never forced onto the question.

**When the manual is not enough**

The assistant behaves like a technical expert sitting beside the user. It does not dead-end.

14. The manual is always searched first, and grounded answers are preferred.
15. If the manual covers the topic only partly, the answer uses what the manual has, cites it, and
    marks the remainder as general guidance.
16. If the manual does not cover it at all but the question is still a technical question about the
    product — a fault the manual omits, a service centre location, current pricing, a recall — the
    system uses general technical knowledge and web search and **still proposes a solution**.
17. Every answer states its source. Manual-grounded content carries page citations. General guidance
    is clearly marked as not coming from the manual. The two are never presented identically.
18. The system declines only when the question is not about the product at all.
19. Safety-critical topics — brakes, airbags, restraints, towing, jacking — are answered from the
    manual or escalated. They are never answered from general knowledge.

**Escalation**

Escalation is the last resort, not the second option. It happens after the assistant has genuinely
tried — manual first, then general expertise and the web.

20. When the proposed solutions do not work, or the user asks for a person, the conversation is
    handed off for a live agent.
21. The handoff carries the full transcript, what was already tried, which pages were shown, the
    reason for escalating, and a suggested next step.
22. The user sees a confirmation with a reference number.
23. An operator screen lists open handoffs and shows the full package for any one of them. Nothing is
    transmitted to an external helpdesk — see `docs/decisions.md` D12.

## Definition of done

A person can open the app, pick a manual, describe a fault, and watch the assistant work — the steps
it is taking visible as they happen, the answer arriving as it is written, the cited page beside it.
They can tell at a glance which parts came from the manual and which did not. They can close the
browser, come back, reopen the conversation and continue it. When nothing solves the fault, it reaches
a human with everything that human needs, and an operator can see that handoff arrive.

And the eval harness reports a Recall@10 figure that can be quoted in the proposal.

## Corpus

Two BAIC vehicle owner manuals: BJ30/e30 (283 pages) and X55 II (263 pages). 546 pages total.
Both born-digital — no OCR required.

These are the example corpus. The system must work on any manual set, and swapping corpus must not
require code changes. See the document-agnostic rules in `AGENTS.md`.

## Out of scope

Cross-manual comparison, multilingual answers, in-app upload, authentication, dealer integrations,
voice, analytics dashboards, proactive alerts.
