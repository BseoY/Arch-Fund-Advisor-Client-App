import { useCallback, useEffect, useState, type FormEvent, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  getService,
  type Client,
  type ClientOverview,
  type DocumentInput,
  type FundDocument,
  type Session,
} from "@/services";

const TOKEN_KEY = "arch-session-token";
const svc = () => getService();

export const money = (n: number) =>
  n.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
const fmtDate = (d: string) =>
  new Date(d + "T00:00:00").toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

function useAction() {
  const [error, setError] = useState<string | null>(null);
  const run = useCallback(async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong.");
      return false;
    }
  }, []);
  return { error, run };
}

function ErrorLine({ error }: { error: string | null }) {
  return error ? <p className="text-sm text-destructive">{error}</p> : null;
}

export function ArchApp() {
  const [ready, setReady] = useState(false);
  const [hasAdvisor, setHasAdvisor] = useState(false);
  const [session, setSession] = useState<Session | null>(null);
  const [bootError, setBootError] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setHasAdvisor(await svc().hasAdvisor());
        const t = localStorage.getItem(TOKEN_KEY);
        if (t) setSession(await svc().getSession(t));
      } catch (e) {
        setBootError(e instanceof Error ? e.message : "The server is not reachable.");
      } finally {
        setReady(true);
      }
    })();
  }, []);

  const onSession = (s: Session) => {
    localStorage.setItem(TOKEN_KEY, s.token);
    setHasAdvisor(true);
    setSession(s);
  };
  const logout = async () => {
    if (session) await svc().logout(session.token);
    localStorage.removeItem(TOKEN_KEY);
    setSession(null);
  };

  if (!ready) return <div className="min-h-screen" />;
  if (bootError && !session) return <p className="p-8 text-sm text-destructive">{bootError}</p>;
  if (!session) return <SignIn setup={!hasAdvisor} onSession={onSession} />;

  return (
    <div className="min-h-screen">
      <header className="border-b bg-card">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
          <div className="flex items-baseline gap-3">
            <span className="font-display text-2xl font-semibold text-primary">Arch</span>
            <span className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Morning view</span>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-muted-foreground">
              {session.name} · {session.role}
            </span>
            <Button variant="outline" size="sm" onClick={logout}>
              Sign out
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-6 py-8">
        {session.role === "advisor" ? (
          <AdvisorHome token={session.token} />
        ) : (
          <ClientHome token={session.token} clientId={session.clientId!} />
        )}
      </main>
    </div>
  );
}

function SignIn({ setup, onSession }: { setup: boolean; onSession: (s: Session) => void }) {
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const { error, run } = useAction();
  const submit = (e: FormEvent) => {
    e.preventDefault();
    run(async () => onSession(setup ? await svc().setupAdvisor(name, password) : await svc().login(name, password)));
  };
  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={submit} className="w-full max-w-sm space-y-5 rounded-md border bg-card p-8">
        <div>
          <p className="font-display text-3xl font-semibold text-primary">Arch</p>
          <h1 className="mt-2 text-xl">{setup ? "Create the advisor account" : "Sign in"}</h1>
          {setup && <p className="mt-1 text-sm text-muted-foreground">First run. This account manages every client.</p>}
        </div>
        <label className="block space-y-1 text-sm">
          <span>Name</span>
          <Input value={name} onChange={(e) => setName(e.target.value)} autoFocus />
        </label>
        <label className="block space-y-1 text-sm">
          <span>Password</span>
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <ErrorLine error={error} />
        <Button type="submit" className="w-full">
          {setup ? "Create account" : "Sign in"}
        </Button>
      </form>
    </div>
  );
}

/* ---------------- Advisor ---------------- */

function AdvisorHome({ token }: { token: string }) {
  const [clients, setClients] = useState<Client[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [pw, setPw] = useState("");
  const { error, run } = useAction();

  const refresh = useCallback(async () => {
    const list = await svc().listClients(token);
    setClients(list);
    setSelected((s) => (s && list.some((c) => c.id === s) ? s : (list[0]?.id ?? null)));
  }, [token]);
  useEffect(() => {
    refresh();
  }, [refresh]);

  const add = (e: FormEvent) => {
    e.preventDefault();
    run(async () => {
      const c = await svc().createClient(token, name, pw);
      setName("");
      setPw("");
      await refresh();
      setSelected(c.id);
    });
  };

  return (
    <div className="grid gap-8 md:grid-cols-[220px_1fr]">
      <aside className="space-y-6">
        <div>
          <h2 className="mb-2 text-xs font-medium uppercase tracking-[0.2em] text-muted-foreground">Clients</h2>
          <ul className="space-y-1">
            {clients.map((c) => (
              <li key={c.id}>
                <button
                  onClick={() => setSelected(c.id)}
                  className={`w-full rounded-sm px-3 py-2 text-left text-sm transition-colors ${
                    c.id === selected ? "bg-primary text-primary-foreground" : "hover:bg-secondary"
                  }`}
                >
                  {c.name}
                </button>
              </li>
            ))}
            {clients.length === 0 && <li className="text-sm text-muted-foreground">No clients yet.</li>}
          </ul>
        </div>
        <form onSubmit={add} className="space-y-2 border-t pt-4">
          <p className="text-sm font-medium">New client login</p>
          <Input placeholder="Name" value={name} onChange={(e) => setName(e.target.value)} />
          <Input placeholder="Password" type="password" value={pw} onChange={(e) => setPw(e.target.value)} />
          <ErrorLine error={error} />
          <Button type="submit" size="sm" className="w-full">
            Add client
          </Button>
        </form>
      </aside>
      <section>
        {selected ? (
          <AdvisorClient key={selected} token={token} clientId={selected} onClientsChanged={refresh} />
        ) : (
          <p className="text-muted-foreground">Add a client to begin.</p>
        )}
      </section>
    </div>
  );
}

function useOverview(token: string, clientId: string) {
  const [data, setData] = useState<ClientOverview | null>(null);
  const reload = useCallback(async () => setData(await svc().getClientOverview(token, clientId)), [token, clientId]);
  useEffect(() => {
    reload();
  }, [reload]);
  return { data, reload };
}

function AdvisorClient({ token, clientId, onClientsChanged }: { token: string; clientId: string; onClientsChanged: () => Promise<void> }) {
  const { data, reload } = useOverview(token, clientId);
  const { error, run } = useAction();
  const [editing, setEditing] = useState(false);
  const [newName, setNewName] = useState("");
  const [newPw, setNewPw] = useState("");
  const [fundName, setFundName] = useState("");

  if (!data) return null;
  const act = (fn: () => Promise<unknown>) => run(async () => { await fn(); await reload(); });

  return (
    <div className="space-y-10">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-xs uppercase tracking-[0.2em] text-muted-foreground">Client</p>
          <h1 className="text-4xl">{data.client.name}</h1>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { setEditing(!editing); setNewName(data.client.name); setNewPw(""); }}>
            Edit client
          </Button>
          <Button
            variant="destructive"
            size="sm"
            onClick={() => {
              if (confirm(`Delete ${data.client.name}, their login, funds and documents?`))
                run(async () => { await svc().deleteClient(token, clientId); await onClientsChanged(); });
            }}
          >
            Delete client
          </Button>
        </div>
      </div>
      {editing && (
        <form
          className="flex flex-wrap gap-2 rounded-md border bg-card p-4"
          onSubmit={(e) => {
            e.preventDefault();
            run(async () => {
              await svc().updateClient(token, clientId, { name: newName, password: newPw || undefined });
              setEditing(false);
              await reload();
              await onClientsChanged();
            });
          }}
        >
          <Input className="max-w-xs" value={newName} onChange={(e) => setNewName(e.target.value)} />
          <Input className="max-w-xs" type="password" placeholder="New password (optional)" value={newPw} onChange={(e) => setNewPw(e.target.value)} />
          <Button type="submit" size="sm">Save</Button>
        </form>
      )}
      <ErrorLine error={error} />

      <MorningList data={data} />

      <div className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-2xl">Funds</h2>
          <form
            className="flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              act(async () => { await svc().createFund(token, clientId, fundName); setFundName(""); });
            }}
          >
            <Input placeholder="Fund name" value={fundName} onChange={(e) => setFundName(e.target.value)} />
            <Button type="submit" size="sm">Add fund</Button>
          </form>
        </div>
        {data.funds.length === 0 && <p className="text-sm text-muted-foreground">No funds yet.</p>}
        {data.funds.map((f) => (
          <FundCard
            key={f.id}
            title={f.name}
            actions={
              <>
                <Button variant="ghost" size="sm" onClick={() => { const n = prompt("Fund name", f.name); if (n) act(() => svc().updateFund(token, f.id, n)); }}>
                  Rename
                </Button>
                <Button variant="ghost" size="sm" onClick={() => { if (confirm(`Delete ${f.name} and its documents?`)) act(() => svc().deleteFund(token, f.id)); }}>
                  Delete
                </Button>
              </>
            }
          >
            {f.documents.map((d) => (
              <AdvisorDocRow key={d.id} doc={d} token={token} act={act} />
            ))}
            <DocForm submitLabel="File document" onSubmit={(input) => act(() => svc().createDocument(token, f.id, input))} />
          </FundCard>
        ))}
      </div>
    </div>
  );
}

function AdvisorDocRow({ doc, token, act }: { doc: FundDocument; token: string; act: (fn: () => Promise<unknown>) => Promise<boolean> }) {
  const [editing, setEditing] = useState(false);
  if (editing)
    return (
      <DocForm
        initial={doc}
        submitLabel="Save"
        onCancel={() => setEditing(false)}
        onSubmit={async (input) => { const ok = await act(() => svc().updateDocument(token, doc.id, input)); if (ok) setEditing(false); return ok; }}
      />
    );
  return (
    <DocRow
      doc={doc}
      actions={
        <>
          {doc.kind === "capital_call" && (
            <Button variant={doc.paid ? "outline" : "default"} size="sm" onClick={() => act(() => svc().setPaid(token, doc.id, !doc.paid))}>
              {doc.paid ? "Mark unpaid" : "Mark paid"}
            </Button>
          )}
          <Button variant="ghost" size="sm" onClick={() => setEditing(true)}>Edit</Button>
          <Button variant="ghost" size="sm" onClick={() => { if (confirm("Delete this document?")) act(() => svc().deleteDocument(token, doc.id)); }}>
            Delete
          </Button>
        </>
      }
    />
  );
}

function DocForm({
  initial,
  submitLabel,
  onSubmit,
  onCancel,
}: {
  initial?: FundDocument;
  submitLabel: string;
  onSubmit: (input: DocumentInput) => Promise<boolean>;
  onCancel?: () => void;
}) {
  const [kind, setKind] = useState<DocumentInput["kind"]>(initial?.kind ?? "capital_call");
  const [title, setTitle] = useState(initial?.title ?? "");
  const [amount, setAmount] = useState(initial?.kind === "capital_call" ? String(initial.amount) : "");
  const [dueDate, setDueDate] = useState(initial?.kind === "capital_call" ? initial.dueDate : "");
  const [summary, setSummary] = useState(initial?.kind === "investor_letter" ? initial.summary : "");
  const [open, setOpen] = useState(!!initial);

  if (!open)
    return (
      <button onClick={() => setOpen(true)} className="w-full px-4 py-3 text-left text-sm text-primary hover:bg-secondary">
        + File a document
      </button>
    );

  return (
    <form
      className="flex flex-wrap items-center gap-2 bg-secondary px-4 py-3"
      onSubmit={async (e) => {
        e.preventDefault();
        const input: DocumentInput =
          kind === "capital_call" ? { kind, title, amount: Number(amount), dueDate } : { kind, title, summary };
        if (await onSubmit(input)) {
          if (!initial) { setTitle(""); setAmount(""); setDueDate(""); setSummary(""); setOpen(false); }
        }
      }}
    >
      <select
        aria-label="Document type"
        value={kind}
        onChange={(e) => setKind(e.target.value as DocumentInput["kind"])}
        className="h-9 rounded-sm border bg-card px-2 text-sm"
      >
        <option value="capital_call">Capital call</option>
        <option value="investor_letter">Investor letter</option>
      </select>
      <Input className="w-44" placeholder="Title" value={title} onChange={(e) => setTitle(e.target.value)} />
      {kind === "capital_call" ? (
        <>
          <Input className="w-32" type="number" min="0" step="0.01" placeholder="Amount due" value={amount} onChange={(e) => setAmount(e.target.value)} />
          <Input className="w-40" type="date" aria-label="Due date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
        </>
      ) : (
        <Input className="min-w-60 flex-1" placeholder="What changed?" value={summary} onChange={(e) => setSummary(e.target.value)} />
      )}
      <Button type="submit" size="sm">{submitLabel}</Button>
      <Button type="button" variant="ghost" size="sm" onClick={() => (onCancel ? onCancel() : setOpen(false))}>Cancel</Button>
    </form>
  );
}

/* ---------------- Shared ---------------- */

function MorningList({ data }: { data: ClientOverview }) {
  const total = data.morning.reduce((s, m) => s + m.amount, 0);
  return (
    <section className="rounded-md border-2 border-primary bg-card">
      <div className="flex items-baseline justify-between border-b px-5 py-3">
        <h2 className="text-2xl">Unpaid capital calls</h2>
        <span className="font-mono text-sm text-muted-foreground">
          {data.morning.length} · {money(total)}
        </span>
      </div>
      {data.morning.length === 0 ? (
        <p className="px-5 py-6 text-sm text-muted-foreground">Nothing due. All capital calls are paid.</p>
      ) : (
        <ul className="divide-y">
          {data.morning.map((m) => (
            <li key={m.documentId} className="grid grid-cols-[110px_1fr_auto] items-baseline gap-4 px-5 py-3">
              <span className="font-mono text-sm text-accent-foreground">{fmtDate(m.dueDate)}</span>
              <span>
                <span className="font-medium">{m.fundName}</span>
                <span className="text-muted-foreground"> · {m.title}</span>
              </span>
              <span className="font-mono font-medium">{money(m.amount)}</span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function FundCard({ title, actions, children }: { title: string; actions?: ReactNode; children: ReactNode }) {
  return (
    <div className="overflow-hidden rounded-md border bg-card">
      <div className="flex items-center justify-between border-b bg-muted px-4 py-2">
        <h3 className="text-lg">{title}</h3>
        <div className="flex gap-1">{actions}</div>
      </div>
      <div className="divide-y">{children}</div>
    </div>
  );
}

function DocRow({ doc, actions }: { doc: FundDocument; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <span className="rounded-sm border px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-muted-foreground">
            {doc.kind === "capital_call" ? "Capital call" : "Letter"}
          </span>
          <span className="font-medium">{doc.title}</span>
          {doc.kind === "capital_call" && (
            <span className={`text-xs font-medium ${doc.paid ? "text-success" : "text-destructive"}`}>
              {doc.paid ? "Paid" : "Unpaid"}
            </span>
          )}
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {doc.kind === "capital_call" ? (
            <span className="font-mono">{money(doc.amount)} due {fmtDate(doc.dueDate)}</span>
          ) : (
            doc.summary
          )}
        </p>
      </div>
      <div className="flex items-center gap-1">{actions}</div>
    </div>
  );
}

/* ---------------- Client ---------------- */

function ClientHome({ token, clientId }: { token: string; clientId: string }) {
  const { data, reload } = useOverview(token, clientId);
  const { error, run } = useAction();
  if (!data) return null;
  return (
    <div className="space-y-10">
      <h1 className="text-4xl">Your funds</h1>
      <ErrorLine error={error} />
      <MorningList data={data} />
      <div className="space-y-4">
        {data.funds.length === 0 && <p className="text-sm text-muted-foreground">No funds yet.</p>}
        {data.funds.map((f) => (
          <FundCard key={f.id} title={f.name}>
            {f.documents.length === 0 && <p className="px-4 py-3 text-sm text-muted-foreground">No documents.</p>}
            {f.documents.map((d) => (
              <DocRow
                key={d.id}
                doc={d}
                actions={
                  d.kind === "capital_call" && (
                    <label className="flex items-center gap-2 text-sm text-muted-foreground">
                      <input
                        type="checkbox"
                        className="size-4 accent-primary"
                        checked={!!d.checked}
                        onChange={(e) => run(async () => { await svc().setChecked(token, d.id, e.target.checked); await reload(); })}
                      />
                      My checkmark
                    </label>
                  )
                }
              />
            ))}
          </FundCard>
        ))}
      </div>
    </div>
  );
}
