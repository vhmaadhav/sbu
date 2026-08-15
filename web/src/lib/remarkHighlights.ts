type MarkdownNode = {
  type: string;
  value?: string;
  children?: MarkdownNode[];
  data?: { hName?: string };
};

const HIGHLIGHT = /==([^=\n]+)==/g;
const SKIP_CONTENTS = new Set(["code", "inlineCode"]);

function highlightText(node: MarkdownNode): MarkdownNode[] {
  const value = node.value ?? "";
  const nodes: MarkdownNode[] = [];
  let cursor = 0;

  for (const match of value.matchAll(HIGHLIGHT)) {
    const index = match.index ?? 0;
    if (index > cursor) nodes.push({ type: "text", value: value.slice(cursor, index) });
    nodes.push({
      type: "strong",
      data: { hName: "mark" },
      children: [{ type: "text", value: match[1] }],
    });
    cursor = index + match[0].length;
  }

  if (cursor === 0) return [node];
  if (cursor < value.length) nodes.push({ type: "text", value: value.slice(cursor) });
  return nodes;
}

function transform(node: MarkdownNode) {
  if (!node.children || SKIP_CONTENTS.has(node.type)) return;

  node.children = node.children.flatMap((child) => {
    if (child.type === "text") return highlightText(child);
    transform(child);
    return [child];
  });
}

/** Render LLM-selected ==important terms== as semantic <mark> elements. */
export default function remarkHighlights() {
  return transform;
}
