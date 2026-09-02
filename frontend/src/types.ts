export type User = { id: string; name: string };

export type PermissionMode = "ask" | "workspace" | "full";

export type Agent = {
  id: string;
  user_id: string;
  name: string;
  instructions: string;
  model: string;
  permission_mode: PermissionMode;
  kind: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "tool";
  content: string;
  seq: number;
  created_at: string;
};

export type Run = {
  id: string;
  status: "queued" | "running" | "waiting_approval" | "succeeded" | "failed" | "stopped" | "unknown";
  agent_id: string;
  thread_id: string;
  trigger: string;
  created_at: string;
  error?: string | null;
};

export type Approval = { id: string; tool: string; risk: string; arguments: Record<string, unknown> };
export type Artifact = { id: string; run_id: string; name: string; media_type: string; created_at: string };
export type Memory = { id: string; content: string; created_at: string };
export type Routine = { id: string; name: string; prompt: string; cron: string; timezone: string; enabled: number; next_run_at: string };
export type Skill = {
  id: string;
  user_id: string;
  current_version_id: string;
  name: string;
  status: "draft" | "active" | "archived";
  description: string;
  instructions: string;
  version: number;
  published_at?: string | null;
};

export type ThreadSnapshot = {
  thread_id: string;
  messages: Message[];
  active_run: Run | null;
  pending_approval: Approval | null;
  cursor: number;
};
