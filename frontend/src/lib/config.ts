/** The only place environment values are read, mirroring backend/app/config.py. */

export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";

/** Pages mounted at once. PDF.js degrades past ~25, so this leaves room to
 *  scroll a few pages before the window has to move. */
export const PAGE_WINDOW = 10;
