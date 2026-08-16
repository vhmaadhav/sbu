import { normalizeMath } from "@/lib/mathMarkdown";

const PLACEHOLDER_REFERENCE = /\s*\[(?:@\s*)?(?:mm:ss|p\.\s*N)\]/gi;
const DECORATIVE_EMOJI = /\p{Extended_Pictographic}\uFE0F?/gu;
const DECORATIVE_BULLET = /^(\s*)[•●◦▪▫▸▹►‣]\s+/gm;
const OUTER_MARKDOWN_FENCE = /^\s*```(?:markdown|md)?\s*\n([\s\S]*?)\n```\s*$/i;
// Figure-placement scaffolding the generator could not resolve into an image.
const ECHOED_PLACEMENT_TOKEN = /^[ \t]*(?:[-*+][ \t]+)?\[\[FIG:\d+\]\].*$/gm;
const INLINE_PLACEMENT_TOKEN = /[ \t]*\[\[FIG:\d+\]\][ \t]*/g;

export function cleanStudyMarkdown(markdown: string): string {
  const outerFence = markdown.match(OUTER_MARKDOWN_FENCE);

  return normalizeMath(
    (outerFence?.[1] ?? markdown)
      .replace(PLACEHOLDER_REFERENCE, "")
      .replace(DECORATIVE_EMOJI, "")
      .replace(DECORATIVE_BULLET, "$1- ")
      .replace(/^(\s*)\*\s+/gm, "$1- ")
      .replace(ECHOED_PLACEMENT_TOKEN, "")
      .replace(INLINE_PLACEMENT_TOKEN, " "),
  )
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
