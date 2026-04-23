import type { InteractionState, ThreadEnvelope, ThreadSummary } from "@/lib/types";

const backendUrl = process.env.NEXT_PUBLIC_BACKEND_URL?.replace(/\/$/, "") ?? "";

async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(backendUrl ? `${backendUrl}${path}` : path, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return (await response.json()) as T;
}

export function backendRuntimeUrl(): string {
  return backendUrl ? `${backendUrl}/api/copilotkit` : "/api/copilotkit";
}

export async function listThreads(): Promise<ThreadSummary[]> {
  return requestJson<ThreadSummary[]>("/api/chat/threads");
}

export async function createThread(extensionAlias?: string): Promise<ThreadEnvelope> {
  return requestJson<ThreadEnvelope>("/api/chat/threads", {
    method: "POST",
    body: JSON.stringify({
      model_alias: "openai_default",
      extension_alias: extensionAlias ?? null,
    }),
  });
}

export async function getThread(threadId: string): Promise<ThreadEnvelope> {
  return requestJson<ThreadEnvelope>(`/api/chat/threads/${threadId}`);
}

export async function getInteraction(threadId: string): Promise<InteractionState> {
  return requestJson<InteractionState>(`/api/chat/threads/${threadId}/interaction`);
}

export async function deleteThread(threadId: string): Promise<void> {
  await requestJson(`/api/chat/threads/${threadId}`, { method: "DELETE" });
}
