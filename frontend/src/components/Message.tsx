import type { ReactNode } from "react";

type MessageProps = {
  tone?: "info" | "success" | "warning" | "error";
  children: ReactNode;
};

export function Message({ tone = "info", children }: MessageProps) {
  return (
    <div className={`message ${tone}`} role={tone === "error" ? "alert" : "status"}>
      {children}
    </div>
  );
}
