import { Activity, Bot, ChevronDown, FileText, Menu, PanelRight, Plus, Send, ShieldAlert, Sparkles, Wrench, X } from "lucide-react";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { api } from "./api";
import type { Agent, Artifact, Memory, PermissionMode, Routine, Run, Skill, ThreadSnapshot, User } from "./types";

type View = "chat" | "activity" | "skills";

export function App() {
  const [users, setUsers] = useState<User[]>([]);
  const [userId, setUserId] = useState(localStorage.getItem("meta-workers-user") ?? "user_alice");
  const [agents, setAgents] = useState<Agent[]>([]);
  const [agent, setAgent] = useState<Agent | null>(null);
  const [thread, setThread] = useState<ThreadSnapshot | null>(null);
  const [activity, setActivity] = useState<Run[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [memories, setMemories] = useState<Memory[]>([]);
  const [routines, setRoutines] = useState<Routine[]>([]);
  const [skills, setSkills] = useState<Skill[]>([]);
  const [catalog, setCatalog] = useState<Skill[]>([]);
  const [view, setView] = useState<View>("chat");
  const [prompt, setPrompt] = useState("");
  const [stream, setStream] = useState("");
  const [progress, setProgress] = useState("");
  const [error, setError] = useState("");
  const [menu, setMenu] = useState(false);

  const refreshThread = useCallback(async () => {
    if (agent) setThread(await api.thread(userId, agent.id));
  }, [agent, userId]);

  useEffect(() => { api.users().then(setUsers).catch(showError); }, []);
  useEffect(() => {
    localStorage.setItem("meta-workers-user", userId);
    setThread(null);
    api.agents(userId).then((items) => { setAgents(items); setAgent(items[0] ?? null); }).catch(showError);
    api.artifacts(userId).then(setArtifacts).catch(showError);
  }, [userId]);
  useEffect(() => {
    if (!agent) return;
    refreshThread().catch(showError);
    api.memories(userId, agent.id).then(setMemories).catch(showError);
    api.routines(userId, agent.id).then(setRoutines).catch(showError);
  }, [agent, refreshThread, userId]);
  useEffect(() => {
    if (view === "activity") api.activity(userId).then(setActivity).catch(showError);
    if (view === "skills") Promise.all([api.skills(userId), api.catalog()]).then(([own, shared]) => { setSkills(own); setCatalog(shared); }).catch(showError);
  }, [view, userId]);
  useEffect(() => {
    if (!thread || typeof EventSource === "undefined") return;
    const events = new EventSource(`/api/users/${userId}/threads/${thread.thread_id}/events?after=${thread.cursor}`);
    const refresh = () => { setStream(""); refreshThread().catch(showError); api.artifacts(userId).then(setArtifacts).catch(showError); };
    const delta = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setStream((current) => current + String(data.payload?.delta ?? ""));
    };
    const toolStarted = (event: MessageEvent) => {
      const data = JSON.parse(event.data);
      setProgress(`Using ${String(data.payload?.tool ?? "tool")}…`);
      refresh();
    };
    events.addEventListener("assistant.delta", delta as EventListener);
    events.addEventListener("tool.started", toolStarted as EventListener);
    ["run.started", "approval.required", "approval.resolved", "artifact.created"].forEach((name) => events.addEventListener(name, refresh));
    ["run.completed", "run.failed", "run.stopped", "tool.completed"].forEach((name) => events.addEventListener(name, () => { setProgress(""); refresh(); }));
    events.onerror = () => events.close();
    return () => events.close();
  }, [thread?.thread_id, userId]); // refresh cursor only when reconnecting to a different thread

  function showError(cause: unknown) { setError(cause instanceof Error ? cause.message : "Something went wrong"); }
  function chooseAgent(item: Agent) { setAgent(item); setView("chat"); setMenu(false); setStream(""); }

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!agent || !prompt.trim()) return;
    const text = prompt.trim();
    setPrompt(""); setStream("");
    try { await api.run(userId, agent.id, text); await refreshThread(); } catch (cause) { showError(cause); setPrompt(text); }
  }

  async function createAgent() {
    const name = window.prompt("Agent name");
    if (!name?.trim()) return;
    const instructions = window.prompt("What should this agent do?");
    if (!instructions?.trim()) return;
    try {
      const created = await api.createAgent(userId, { name: name.trim(), instructions: instructions.trim() });
      setAgents((items) => [...items, created]); chooseAgent(created);
    } catch (cause) { showError(cause); }
  }

  async function changePermission(mode: PermissionMode) {
    if (!agent || (mode === "full" && !window.confirm("Full access runs tools without approval. Enable it for this trusted POC user?"))) return;
    try {
      const updated = await api.updatePermission(userId, agent.id, mode);
      setAgent(updated); setAgents((items) => items.map((item) => item.id === updated.id ? updated : item));
    } catch (cause) { showError(cause); }
  }

  async function decide(decision: "approve" | "deny") {
    if (!thread?.active_run || !thread.pending_approval) return;
    try { await api.decide(userId, thread.active_run.id, thread.pending_approval.id, decision); await refreshThread(); } catch (cause) { showError(cause); }
  }

  async function createRoutine() {
    if (!agent) return;
    const name = window.prompt("Routine name"); const routinePrompt = window.prompt("Prompt to run"); const cron = window.prompt("Cron schedule", "0 9 * * 1");
    if (!name || !routinePrompt || !cron) return;
    try {
      const created = await api.createRoutine(userId, agent.id, { name, prompt: routinePrompt, cron, timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC" });
      setRoutines((items) => [...items, created]);
    } catch (cause) { showError(cause); }
  }

  function openView(next: View) { setView(next); setMenu(false); }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${menu ? "open" : ""}`} aria-label="Coworkers">
        <div className="brand"><Sparkles size={18} /> <strong>Meta Workers</strong><button className="mobile-close" onClick={() => setMenu(false)} aria-label="Close menu"><X size={18} /></button></div>
        <label className="user-select"><span>Demo user</span><span className="select-wrap"><select value={userId} onChange={(event) => setUserId(event.target.value)}>{users.map((user) => <option key={user.id} value={user.id}>{user.name}</option>)}</select><ChevronDown size={14} /></span></label>
        <div className="demo-warning"><ShieldAlert size={15} /> Trusted POC · no authentication</div>
        <button className="new-agent" onClick={createAgent}><Plus size={15} /> New agent</button>
        <nav className="agent-list" aria-label="Agent list">
          {agents.map((item) => <button key={item.id} className={agent?.id === item.id && view === "chat" ? "agent active" : "agent"} onClick={() => chooseAgent(item)}><span className="avatar"><Bot size={16} /></span><span><strong>{item.name}</strong><small>{item.kind === "kyc" ? "Public-company research" : item.kind === "skills" ? "Draft internal skills" : "Custom coworker"}</small></span></button>)}
        </nav>
        <button className="activity-link" onClick={() => openView("skills")}><Wrench size={16} /> Skills</button>
        <button className="activity-link bottom" onClick={() => openView("activity")}><Activity size={16} /> Activity</button>
      </aside>

      <main id="workspace" className="workspace">
        <header className="workspace-header">
          <button className="mobile-menu" onClick={() => setMenu(true)} aria-label="Open menu"><Menu size={18} /></button>
          <div><h1>{view === "chat" ? agent?.name ?? "Choose an agent" : view === "activity" ? "Activity" : "Skills"}</h1><p>{view === "chat" ? agent?.model ?? "" : view === "activity" ? "Recent agent runs" : "Private instructions and shared copies"}</p></div>
          <button className="icon-button" aria-label="Agent settings"><PanelRight size={18} /></button>
        </header>
        {view === "chat" && <Chat thread={thread} stream={stream} progress={progress} agent={agent} users={users} userId={userId} prompt={prompt} setPrompt={setPrompt} submit={submit} decide={decide} stop={() => thread?.active_run && api.stop(userId, thread.active_run.id).then(refreshThread).catch(showError)} />}
        {view === "activity" && <ActivityView runs={activity} agents={agents} />}
        {view === "skills" && <SkillsView userId={userId} agents={agents} skills={skills} catalog={catalog} reload={() => Promise.all([api.skills(userId), api.catalog()]).then(([own, shared]) => { setSkills(own); setCatalog(shared); })} onError={showError} />}
        {error && <button className="error-toast" role="alert" onClick={() => setError("")}>{error}</button>}
      </main>

      <aside className="inspector" aria-label="Agent context">
        <h2>Agent</h2>
        <dl><dt>Permission</dt><dd>{agent && <select value={agent.permission_mode} onChange={(event) => changePermission(event.target.value as PermissionMode)}><option value="ask">Ask</option><option value="workspace">Workspace</option><option value="full">Full access</option></select>}</dd><dt>Computer</dt><dd>{thread?.active_run ? "Active" : "Idle"}</dd><dt>Memory</dt><dd>{memories.length} items</dd><dt>Routines</dt><dd>{routines.length}</dd></dl>
        <button className="inspector-action" onClick={createRoutine}>Add routine</button>
        {agent?.permission_mode === "full" && <p className="risk-note">Tools run without confirmation, inside this user’s container only.</p>}
        <div className="divider" /><h2>Instructions</h2><p>{agent?.instructions}</p>
        <div className="divider" /><h2>Artifacts</h2><div className="artifact-list">{artifacts.filter((item) => !thread?.active_run || item.run_id === thread.active_run.id).slice(0, 8).map((item) => <a key={item.id} href={`/api/users/${userId}/artifacts/${item.id}`}><FileText size={14} />{item.name}</a>)}{!artifacts.length && <p>None yet.</p>}</div>
      </aside>
    </div>
  );
}

function Chat({ thread, stream, progress, agent, users, userId, prompt, setPrompt, submit, decide, stop }: { thread: ThreadSnapshot | null; stream: string; progress: string; agent: Agent | null; users: User[]; userId: string; prompt: string; setPrompt: (value: string) => void; submit: (event: FormEvent) => void; decide: (value: "approve" | "deny") => void; stop: () => void }) {
  return <><section className="transcript" aria-live="polite" aria-busy={thread?.active_run != null}>
    {!thread?.messages.length && agent && <div className="empty-state"><span className="avatar large"><Bot size={24} /></span><h2>What should {agent.name} work on?</h2><p>{agent.instructions}</p></div>}
    {thread?.messages.filter((message) => message.role !== "tool").map((message) => <article key={message.id} className={`message ${message.role}`}><span>{message.role === "user" ? users.find((user) => user.id === userId)?.name : agent?.name}</span><p>{message.content}</p></article>)}
    {stream && <article className="message assistant"><span>{agent?.name}</span><p>{stream}</p></article>}
    {thread?.pending_approval && <article className="approval-card"><ShieldAlert size={18} /><div><strong>Approve {thread.pending_approval.tool}?</strong><p>{JSON.stringify(thread.pending_approval.arguments)}</p><button onClick={() => decide("deny")}>Deny</button><button className="primary" onClick={() => decide("approve")}>Approve once</button></div></article>}
    {progress && <div className="run-status" role="status">{progress}</div>}
    {thread?.active_run && !thread.pending_approval && <div className="run-status" role="status">{thread.active_run.status.replace("_", " ")}… <button onClick={stop}>Stop</button></div>}
  </section><form className="composer" onSubmit={submit}><label htmlFor="prompt" className="sr-only">Message {agent?.name}</label><textarea id="prompt" value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Ask for a finished outcome…" rows={2} disabled={!agent || !!thread?.active_run} /><button type="submit" aria-label="Send message" disabled={!prompt.trim() || !agent || !!thread?.active_run}><Send size={17} /></button></form></>;
}

function ActivityView({ runs, agents }: { runs: Run[]; agents: Agent[] }) {
  return <section className="page-list"><h2>Recent runs</h2>{runs.map((run) => <article key={run.id} className="list-card"><div><strong>{agents.find((agent) => agent.id === run.agent_id)?.name ?? "Agent"}</strong><p>{new Date(run.created_at).toLocaleString()} · {run.trigger}</p></div><span className={`status ${run.status}`}>{run.status.replace("_", " ")}</span></article>)}{!runs.length && <p>No runs yet.</p>}</section>;
}

function SkillsView({ userId, agents, skills, catalog, reload, onError }: { userId: string; agents: Agent[]; skills: Skill[]; catalog: Skill[]; reload: () => Promise<unknown>; onError: (error: unknown) => void }) {
  async function create() {
    const name = window.prompt("Skill name (lowercase-with-dashes)"); const description = window.prompt("Short description"); const instructions = window.prompt("Instructions");
    if (!name || !description || !instructions) return;
    try { await api.createSkill(userId, { name, description, instructions }); await reload(); } catch (error) { onError(error); }
  }
  async function act(action: () => Promise<unknown>) { try { await action(); await reload(); } catch (error) { onError(error); } }
  return <section className="page-list"><div className="page-title"><h2>Your skills</h2><button className="primary" onClick={create}><Plus size={14} /> New skill</button></div>{skills.map((skill) => <article className="skill-card" key={skill.id}><div><strong>{skill.name}</strong><p>{skill.description}</p><small>v{skill.version} · {skill.status}</small></div><div className="card-actions">{skill.status === "draft" && <button onClick={() => act(() => api.activateSkill(userId, skill.id))}>Activate</button>}{skill.status === "active" && <><button onClick={() => agents[0] && act(() => api.assignSkill(userId, skill.id, agents[0].id))}>Assign to {agents[0]?.name}</button>{!skill.published_at && <button onClick={() => act(() => api.publishSkill(userId, skill.id))}>Publish copy</button>}</>}</div></article>)}<div className="divider" /><h2>Shared catalog</h2>{catalog.map((skill) => <article className="skill-card" key={skill.current_version_id}><div><strong>{skill.name}</strong><p>{skill.description}</p><small>Published copy</small></div><button onClick={() => act(() => api.installSkill(userId, skill.current_version_id))}>Install</button></article>)}</section>;
}
