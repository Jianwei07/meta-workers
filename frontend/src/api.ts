import type { Agent, Artifact, Memory, PermissionMode, Routine, Run, Skill, ThreadSnapshot, User } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({ error: { message: response.statusText } }));
    throw new Error(body.error?.message ?? response.statusText);
  }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>;
}

const post = <T>(path: string, body?: unknown) => request<T>(path, {
  method: "POST", body: body === undefined ? undefined : JSON.stringify(body),
});

export const api = {
  users: () => request<User[]>("/api/users"),
  agents: (userId: string) => request<Agent[]>(`/api/users/${userId}/agents`),
  createAgent: (userId: string, body: { name: string; instructions: string }) => post<Agent>(`/api/users/${userId}/agents`, body),
  updatePermission: (userId: string, agentId: string, permission_mode: PermissionMode) => request<Agent>(`/api/users/${userId}/agents/${agentId}`, {
    method: "PATCH", body: JSON.stringify({ permission_mode }),
  }),
  thread: (userId: string, agentId: string) =>
    request<ThreadSnapshot>(`/api/users/${userId}/agents/${agentId}/thread`),
  run: (userId: string, agentId: string, prompt: string) =>
    post<Run>(`/api/users/${userId}/agents/${agentId}/runs`, { prompt, client_nonce: crypto.randomUUID() }),
  stop: (userId: string, runId: string) => post<Run>(`/api/users/${userId}/runs/${runId}/stop`),
  decide: (userId: string, runId: string, approvalId: string, decision: "approve" | "deny") => post<Run>(`/api/users/${userId}/runs/${runId}/approvals/${approvalId}`, { decision }),
  activity: (userId: string) => request<Run[]>(`/api/users/${userId}/activity`),
  artifacts: (userId: string) => request<Artifact[]>(`/api/users/${userId}/artifacts`),
  memories: (userId: string, agentId: string) => request<Memory[]>(`/api/users/${userId}/agents/${agentId}/memories`),
  routines: (userId: string, agentId: string) => request<Routine[]>(`/api/users/${userId}/agents/${agentId}/routines`),
  createRoutine: (userId: string, agentId: string, body: { name: string; prompt: string; cron: string; timezone: string }) => post<Routine>(`/api/users/${userId}/agents/${agentId}/routines`, body),
  skills: (userId: string) => request<Skill[]>(`/api/users/${userId}/skills`),
  catalog: () => request<Skill[]>("/api/catalog/skills"),
  createSkill: (userId: string, body: { name: string; description: string; instructions: string }) => post<Skill>(`/api/users/${userId}/skills`, body),
  activateSkill: (userId: string, skillId: string) => post<Skill>(`/api/users/${userId}/skills/${skillId}/activate`),
  assignSkill: (userId: string, skillId: string, agentId: string) => post<void>(`/api/users/${userId}/skills/${skillId}/assign`, { agent_id: agentId }),
  publishSkill: (userId: string, skillId: string) => post<Skill>(`/api/users/${userId}/skills/${skillId}/publish`),
  installSkill: (userId: string, versionId: string) => post<Skill>(`/api/users/${userId}/catalog/${versionId}/install`),
};
