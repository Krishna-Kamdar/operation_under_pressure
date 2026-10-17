import { FormEvent, StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BrowserRouter, Link, Route, Routes, useNavigate, useParams, useSearchParams } from "react-router-dom";

import { api, ApiError, isAuthenticated, setToken, Status, WorkItem } from "./api";
import "./styles.css";

const queryClient = new QueryClient();

function Login({ onLogin }: { onLogin?: () => void }) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("member@example.com");
  const [password, setPassword] = useState("ChangeMe123!");
  const [error, setError] = useState("");
  const mutation = useMutation({
    mutationFn: () => api.login(email.trim().toLowerCase(), password),
    onSuccess: (data) => {
      setToken(data.access_token);
      queryClient.setQueryData(["me"], data.user);
      onLogin?.();
      navigate("/");
    },
    onError: (error: Error) => setError(error.message),
  });
  function submit(event: FormEvent) {
    event.preventDefault();
    mutation.mutate();
  }
  return (
    <main className="auth-shell">
      <form className="panel auth-card" onSubmit={submit}>
        <p className="eyebrow">OPERATIONS UNDER PRESSURE</p>
        <h1>Sign in to your operations desk</h1>
        <label>Email<input value={email} onChange={(event) => setEmail(event.target.value)} type="email" /></label>
        <label>Password<input value={password} onChange={(event) => setPassword(event.target.value)} type="password" /></label>
        {error && <p className="error">{error}</p>}
        <button disabled={mutation.isPending}>{mutation.isPending ? "Signing in..." : "Sign in"}</button>
        <small>Demo accounts use the seeded password: ChangeMe123!</small>
      </form>
    </main>
  );
}

function Layout({ children, onSignOut }: { children: React.ReactNode; onSignOut: () => void }) {
  const navigate = useNavigate();
  const user = useQuery({ queryKey: ["me"], queryFn: api.me });
  function signOut() {
    setToken(null);
    queryClient.clear();
    onSignOut();
    navigate("/login", { replace: true });
  }
  return (
    <div className="app-shell">
      <header className="topbar">
        <Link className="brand" to="/">OPS<span>PRESSURE</span></Link>
        <div className="user-menu">
          <span>{user.data?.display_name ?? "Loading..."}</span>
          <button className="button-quiet" onClick={signOut}>Sign out</button>
        </div>
      </header>
      {children}
    </div>
  );
}

function Dashboard() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [search, setSearch] = useState(searchParams.get("q") ?? "");
  const view = searchParams.get("view") ?? "assigned";
  const params = new URLSearchParams({ limit: "25" });
  if (search) params.set("q", search);
  if (view === "assigned") params.set("assigned_to_me", "true");
  if (view === "urgent") params.set("urgent", "true");
  if (view === "approval") params.set("awaiting_my_approval", "true");
  const items = useQuery({ queryKey: ["items", params.toString()], queryFn: () => api.items(params) });
  const user = useQuery({ queryKey: ["me"], queryFn: api.me });
  const teams = useQuery({ queryKey: ["teams"], queryFn: api.teams });
  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState("");
  const create = useMutation({
    mutationFn: api.createItem,
    onSuccess: (data) => {
      setShowCreate(false);
      setCreateError("");
      client.invalidateQueries({ queryKey: ["items"] });
      navigate(`/items/${data.id}`);
    },
    onError: (error: ApiError) => setCreateError(error.message),
  });
  function changeView(nextView: string) {
    setSearchParams({ view: nextView, ...(search ? { q: search } : {}) });
  }
  return (
    <>
      <section className="hero">
        <div><p className="eyebrow">CONTROL CENTER</p><h1>Make the next action obvious.</h1><p className="muted">Track ownership, urgency, and approvals across your teams.</p></div>
        <div className="hero-stat"><strong>{items.data?.items.length ?? "—"}</strong><span>visible items</span></div>
      </section>
      <nav className="tabs">
        <button className={view === "assigned" ? "active" : ""} onClick={() => changeView("assigned")}>Assigned to me</button>
        <button className={view === "urgent" ? "active" : ""} onClick={() => changeView("urgent")}>Unassigned urgent</button>
        <button className={view === "approval" ? "active" : ""} onClick={() => changeView("approval")}>Awaiting approval</button>
      </nav>
      <section className="panel filters">
        <input value={search} onChange={(event) => setSearch(event.target.value)} onKeyDown={(event) => event.key === "Enter" && setSearchParams({ view, q: search })} placeholder="Search title or description..." />
        <button onClick={() => setSearchParams({ view, ...(search ? { q: search } : {}) })}>Search</button>
        {user.data && Object.values(user.data.team_roles).some((role) => role !== "viewer") && <button onClick={() => setShowCreate((value) => !value)}>Add work item</button>}
      </section>
      {showCreate && <CreateItemForm teams={teams.data ?? []} onSubmit={(input) => create.mutate(input)} isPending={create.isPending} error={createError} />}
      {items.isLoading && <p className="muted">Loading work items...</p>}
      {items.isError && <p className="error">Unable to load items. Check that the API is running.</p>}
      <section className="item-list">
        {items.data?.items.map((item) => <ItemRow key={item.id} item={item} />)}
        {!items.isLoading && items.data?.items.length === 0 && <div className="panel empty"><h2>Nothing needs attention here.</h2><p className="muted">Try another view or search term.</p></div>}
      </section>
    </>
  );
}

function CreateItemForm({ teams, onSubmit, isPending, error }: {
  teams: { id: string; name: string }[];
  onSubmit: (input: { title: string; description: string; item_type: "incident" | "customer_issue" | "payment" | "compliance" | "task"; priority: "low" | "medium" | "high" | "urgent"; team_id: string }) => void;
  isPending: boolean;
  error: string;
}) {
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [teamId, setTeamId] = useState(teams[0]?.id ?? "");
  const [itemType, setItemType] = useState<"incident" | "customer_issue" | "payment" | "compliance" | "task">("incident");
  const [priority, setPriority] = useState<"low" | "medium" | "high" | "urgent">("medium");
  useEffect(() => {
    if (!teamId && teams[0]) setTeamId(teams[0].id);
  }, [teamId, teams]);
  return <form className="panel create-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title, description, item_type: itemType, priority, team_id: teamId }); }}>
    <h2>Add work item</h2>
    <div className="form-grid">
      <label>Title<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
      <label>Team<select required value={teamId} onChange={(event) => setTeamId(event.target.value)}>{teams.map((team) => <option value={team.id} key={team.id}>{team.name}</option>)}</select></label>
      <label>Type<select value={itemType} onChange={(event) => setItemType(event.target.value as typeof itemType)}><option value="incident">Incident</option><option value="customer_issue">Customer issue</option><option value="payment">Payment</option><option value="compliance">Compliance</option><option value="task">Task</option></select></label>
      <label>Priority<select value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
    </div>
    <label>Description<textarea required value={description} onChange={(event) => setDescription(event.target.value)} /></label>
    {error && <p className="error">{error}</p>}
    <button disabled={isPending || !teamId}>{isPending ? "Creating..." : "Create work item"}</button>
  </form>;
}

function ItemRow({ item }: { item: WorkItem }) {
  return <Link className="item-row panel" to={`/items/${item.id}`}><div className={`priority-dot ${item.priority}`} /><div className="item-main"><div className="item-title">{item.title}</div><div className="muted">{item.item_type.replace("_", " ")} · Updated {new Date(item.updated_at).toLocaleString()}</div></div><span className={`badge ${item.status}`}>{item.status.replace("_", " ")}</span><span className="priority-label">{item.priority}</span></Link>;
}

function ItemDetail() {
  const { id = "" } = useParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const item = useQuery({ queryKey: ["item", id], queryFn: () => api.item(id) });
  const activity = useQuery({ queryKey: ["activity", id], queryFn: () => api.activity(id), enabled: Boolean(item.data) });
  const user = useQuery({ queryKey: ["me"], queryFn: api.me });
  const [comment, setComment] = useState("");
  const [error, setError] = useState("");
  const [editing, setEditing] = useState(false);
  const claim = useMutation({ mutationFn: () => api.claim(id), onSuccess: (data) => client.setQueryData(["item", id], data), onError: (error: ApiError) => setError(error.message) });
  const unassign = useMutation({ mutationFn: () => api.unassign(id), onSuccess: (data) => { client.setQueryData(["item", id], data); client.invalidateQueries({ queryKey: ["activity", id] }); }, onError: (error: ApiError) => setError(error.message) });
  const transition = useMutation({ mutationFn: (status: Status) => api.transition(id, status, item.data?.version ?? 0), onSuccess: (data) => { client.setQueryData(["item", id], data); client.invalidateQueries({ queryKey: ["activity", id] }); }, onError: (error: ApiError) => setError(error.message) });
  const addComment = useMutation({ mutationFn: () => api.createComment(id, comment), onSuccess: () => { setComment(""); client.invalidateQueries({ queryKey: ["activity", id] }); }, onError: (error: ApiError) => setError(error.message) });
  const update = useMutation({
    mutationFn: (input: { title: string; description: string; priority: "low" | "medium" | "high" | "urgent"; expected_version: number }) => api.updateItem(id, input),
    onSuccess: (data) => { setEditing(false); setError(""); client.setQueryData(["item", id], data); client.invalidateQueries({ queryKey: ["activity", id] }); },
    onError: (error: ApiError) => setError(error.message),
  });
  if (item.isLoading) return <p className="muted">Loading item...</p>;
  if (item.isError || !item.data) return <div className="panel"><p className="error">This item could not be loaded.</p><button onClick={() => navigate("/")}>Back to dashboard</button></div>;
  const current = item.data;
  const canApprove = user.data?.team_roles[current.team_id] === "lead" || user.data?.team_roles[current.team_id] === "admin";
  const role = user.data?.team_roles[current.team_id];
  const canMutate = role !== undefined && role !== "viewer";
  const canUnassign = current.assignee_id === user.data?.id || role === "lead" || role === "admin";
  const nextStatus: Partial<Record<Status, Status>> = { open: "in_progress", in_progress: "awaiting_approval", awaiting_approval: "resolved", resolved: "closed" };
  const next = nextStatus[current.status];
  return (
    <>
      <button className="back-link" onClick={() => navigate("/")}>← Back to dashboard</button>
      <section className="detail-grid">
        <div>
          <section className="panel detail-card"><div className="detail-heading"><div><p className="eyebrow">{current.item_type.replace("_", " ")}</p><h1>{current.title}</h1></div><span className={`badge ${current.status}`}>{current.status.replace("_", " ")}</span></div>{editing ? <EditItemForm item={current} isPending={update.isPending} onCancel={() => setEditing(false)} onSubmit={(input) => update.mutate(input)} /> : <><p className="description">{current.description}</p><div className="metadata"><div><span>Priority</span><strong>{current.priority}</strong></div><div><span>Version</span><strong>{current.version}</strong></div><div><span>Due</span><strong>{current.due_at ? new Date(current.due_at).toLocaleDateString() : "No due date"}</strong></div></div><div className="actions">{canMutate && <button className="button-secondary" onClick={() => setEditing(true)}>Edit</button>}{!current.assignee_id && canMutate && <button onClick={() => claim.mutate()} disabled={claim.isPending}>{claim.isPending ? "Claiming..." : "Claim this item"}</button>}{current.assignee_id && canUnassign && <button className="button-secondary" onClick={() => unassign.mutate()} disabled={unassign.isPending}>{unassign.isPending ? "Unassigning..." : "Unassign item"}</button>}{next && (current.status !== "awaiting_approval" || canApprove) && <button className="button-secondary" onClick={() => transition.mutate(next)} disabled={transition.isPending}>{transition.isPending ? "Updating..." : `Move to ${next.replace("_", " ")}`}</button>}{current.status === "awaiting_approval" && !canApprove && <p className="muted approval-note">Awaiting approval from a team Lead or Admin.</p>}</div></>}{error && <p className="error">{error} {error.includes("changed") && "Refresh the page before trying again."}</p>}</section>
          <section className="panel comment-card"><h2>Add a comment</h2><textarea value={comment} onChange={(event) => setComment(event.target.value)} placeholder="Record an observation or next step..." /><button onClick={() => addComment.mutate()} disabled={!comment.trim() || addComment.isPending}>Post comment</button></section>
        </div>
        <aside className="panel activity-card"><h2>Activity timeline</h2>{activity.isLoading && <p className="muted">Loading history...</p>}{activity.data?.map((event) => <div className="activity-event" key={event.id}><div className="timeline-dot" /><div><strong>{event.event_type === "unassigned" ? "Unassigned" : event.event_type.replace("_", " ")}</strong><p className="muted">{new Date(event.created_at).toLocaleString()}</p><small>{JSON.stringify(event.payload)}</small></div></div>)}</aside>
      </section>
    </>
  );
}

function EditItemForm({ item, isPending, onCancel, onSubmit }: {
  item: WorkItem;
  isPending: boolean;
  onCancel: () => void;
  onSubmit: (input: { title: string; description: string; priority: "low" | "medium" | "high" | "urgent"; expected_version: number }) => void;
}) {
  const [title, setTitle] = useState(item.title);
  const [description, setDescription] = useState(item.description);
  const [priority, setPriority] = useState(item.priority);
  return <form className="edit-form" onSubmit={(event) => { event.preventDefault(); onSubmit({ title, description, priority, expected_version: item.version }); }}>
    <label>Title<input required value={title} onChange={(event) => setTitle(event.target.value)} /></label>
    <label>Description<textarea required value={description} onChange={(event) => setDescription(event.target.value)} /></label>
    <label>Priority<select value={priority} onChange={(event) => setPriority(event.target.value as typeof priority)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option><option value="urgent">Urgent</option></select></label>
    <div className="actions"><button disabled={isPending}>{isPending ? "Saving..." : "Save changes"}</button><button type="button" className="button-secondary" onClick={onCancel}>Cancel</button></div>
  </form>;
}

function ProtectedApp() {
  const [signedOut, setSignedOut] = useState(false);
  const auth = useQuery({ queryKey: ["me"], queryFn: api.me, retry: false });
  if (signedOut || !isAuthenticated()) return <Login onLogin={() => setSignedOut(false)} />;
  if (auth.isLoading) return <main className="auth-shell"><p>Loading...</p></main>;
  if (auth.isError) return <Login />;
  return <Layout onSignOut={() => setSignedOut(true)}><Routes><Route path="/" element={<Dashboard />} /><Route path="/items/:id" element={<ItemDetail />} /></Routes></Layout>;
}

function App() {
  return <BrowserRouter><ProtectedApp /></BrowserRouter>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}><App /></QueryClientProvider>
  </StrictMode>,
);
