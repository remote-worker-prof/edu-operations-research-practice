"use client";

import { useState } from "react";

import { CopilotKit } from "@copilotkit/react-core";

import { ChatShell } from "@/components/chat-shell";
import { backendRuntimeUrl } from "@/lib/api";

export default function Page() {
  const [threadId, setThreadId] = useState<string | undefined>();

  return (
    <CopilotKit
      agent="edu_or_chat"
      runtimeUrl={backendRuntimeUrl()}
      threadId={threadId}
    >
      <ChatShell onThreadIdChange={setThreadId} threadId={threadId} />
    </CopilotKit>
  );
}
