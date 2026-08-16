import type { ReactNode } from "react";
import MonoLabel from "./MonoLabel";

/** Panel header row: mono title on the left, optional action node on the right,
 *  separated from the body by a hairline bottom border. */
export default function SectionHeader({
  title,
  action,
}: {
  title: string;
  action?: ReactNode;
}) {
  return (
    <div
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        gap: 16,
        padding: "16px 22px",
        borderBottom: "1px solid var(--line)",
      }}
    >
      <MonoLabel>{title}</MonoLabel>
      {action}
    </div>
  );
}
