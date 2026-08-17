// Serve the PDF.js worker from public/ instead of a CDN: everything runs locally.
//
// Resolved through react-pdf rather than from the top-level pdfjs-dist. react-pdf
// pins its own copy, and the two can differ — which fails at runtime with
// "The API version ... does not match the Worker version ...".

import { copyFileSync } from "node:fs";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const fromReactPdf = createRequire(require.resolve("react-pdf"));
const source = fromReactPdf.resolve("pdfjs-dist/build/pdf.worker.min.mjs");

copyFileSync(source, "public/pdf.worker.min.mjs");

const { version } = fromReactPdf("pdfjs-dist/package.json");
console.log(`pdf worker ${version} -> public/pdf.worker.min.mjs`);
