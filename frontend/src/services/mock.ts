import {
  ServiceError,
  type ArchService,
  type Client,
  type ClientOverview,
  type DocumentInput,
  type Fund,
  type FundDocument,
  type Session,
} from "./types";

/** Minimal key-value store; localStorage in the browser, a Map in tests. */
export interface KV {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
}

interface UserRow {
  id: string;
  role: "advisor" | "client";
  name: string;
  salt: string;
  hash: string;
  clientId?: string;
}
interface DocRow {
  id: string;
  fundId: string;
  createdAt: string;
  data: DocumentInput;
  paid: boolean;
}
interface DB {
  users: UserRow[];
  clients: Client[];
  funds: Fund[];
  documents: DocRow[];
  /** key: `${clientId}:${documentId}` */
  checks: string[];
  sessions: Record<string, string>; // token -> userId
}

const KEY = "arch-morning-view-db-v1";
const empty = (): DB => ({ users: [], clients: [], funds: [], documents: [], checks: [], sessions: {} });

const uid = () => crypto.randomUUID();

async function hashPassword(password: string, salt: string) {
  const buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(`${salt}:${password}`));
  return Array.from(new Uint8Array(buf), (b) => b.toString(16).padStart(2, "0")).join("");
}

function validateDoc(input: DocumentInput): DocumentInput {
  const title = input.title?.trim();
  if (!title) throw new ServiceError("A document needs a title.");
  if (input.kind === "capital_call") {
    if (!(input.amount > 0)) throw new ServiceError("Amount due must be greater than zero.");
    if (!/^\d{4}-\d{2}-\d{2}$/.test(input.dueDate)) throw new ServiceError("Due date is required.");
    return { kind: "capital_call", title, amount: input.amount, dueDate: input.dueDate };
  }
  if (input.kind === "investor_letter") {
    const summary = input.summary?.trim();
    if (!summary) throw new ServiceError("An investor letter needs a summary.");
    return { kind: "investor_letter", title, summary };
  }
  throw new ServiceError("Unknown document type.");
}

export function createMockService(kv: KV): ArchService {
  const load = (): DB => {
    const raw = kv.getItem(KEY);
    return raw ? { ...empty(), ...JSON.parse(raw) } : empty();
  };
  const save = (db: DB) => kv.setItem(KEY, JSON.stringify(db));

  const userFor = (db: DB, token: string) => {
    const id = db.sessions[token];
    const u = id && db.users.find((x) => x.id === id);
    if (!u) throw new ServiceError("Please sign in again.");
    return u;
  };
  const advisor = (db: DB, token: string) => {
    const u = userFor(db, token);
    if (u.role !== "advisor") throw new ServiceError("Only the advisor can do that.");
    return u;
  };
  const toSession = (u: UserRow, token: string): Session => ({
    token,
    role: u.role,
    name: u.name,
    clientId: u.clientId,
  });
  const startSession = (db: DB, u: UserRow) => {
    const token = uid();
    db.sessions[token] = u.id;
    save(db);
    return toSession(u, token);
  };
  const nameTaken = (db: DB, name: string, exceptId?: string) =>
    db.users.some((u) => u.name.toLowerCase() === name.toLowerCase() && u.id !== exceptId);
  const fund = (db: DB, id: string) => {
    const f = db.funds.find((x) => x.id === id);
    if (!f) throw new ServiceError("Fund not found.");
    return f;
  };
  const doc = (db: DB, id: string) => {
    const d = db.documents.find((x) => x.id === id);
    if (!d) throw new ServiceError("Document not found.");
    return d;
  };
  const view = (d: DocRow): FundDocument => ({
    ...d.data,
    id: d.id,
    fundId: d.fundId,
    createdAt: d.createdAt,
    ...(d.data.kind === "capital_call" ? { paid: d.paid } : {}),
  });
  const removeDocs = (db: DB, ids: Set<string>) => {
    db.documents = db.documents.filter((d) => !ids.has(d.id));
    db.checks = db.checks.filter((c) => !ids.has(c.split(":")[1]));
  };

  return {
    async hasAdvisor() {
      return load().users.some((u) => u.role === "advisor");
    },
    async setupAdvisor(name, password) {
      const db = load();
      if (db.users.some((u) => u.role === "advisor")) throw new ServiceError("The advisor already exists.");
      if (!name.trim() || !password) throw new ServiceError("Name and password are required.");
      const salt = uid();
      const u: UserRow = { id: uid(), role: "advisor", name: name.trim(), salt, hash: await hashPassword(password, salt) };
      db.users.push(u);
      return startSession(db, u);
    },
    async login(name, password) {
      const db = load();
      const u = db.users.find((x) => x.name.toLowerCase() === name.trim().toLowerCase());
      if (!u || (await hashPassword(password, u.salt)) !== u.hash) throw new ServiceError("Wrong name or password.");
      return startSession(db, u);
    },
    async getSession(token) {
      const db = load();
      const id = db.sessions[token];
      const u = id && db.users.find((x) => x.id === id);
      return u ? toSession(u, token) : null;
    },
    async logout(token) {
      const db = load();
      delete db.sessions[token];
      save(db);
    },

    async listClients(token) {
      const db = load();
      advisor(db, token);
      return [...db.clients].sort((a, b) => a.name.localeCompare(b.name));
    },
    async createClient(token, name, password) {
      const db = load();
      advisor(db, token);
      name = name.trim();
      if (!name || !password) throw new ServiceError("Name and password are required.");
      if (nameTaken(db, name)) throw new ServiceError("That name is already used.");
      const client: Client = { id: uid(), name };
      const salt = uid();
      db.clients.push(client);
      db.users.push({ id: uid(), role: "client", name, salt, hash: await hashPassword(password, salt), clientId: client.id });
      save(db);
      return client;
    },
    async updateClient(token, id, patch) {
      const db = load();
      advisor(db, token);
      const c = db.clients.find((x) => x.id === id);
      const u = db.users.find((x) => x.clientId === id);
      if (!c || !u) throw new ServiceError("Client not found.");
      if (patch.name !== undefined) {
        const name = patch.name.trim();
        if (!name) throw new ServiceError("Name is required.");
        if (nameTaken(db, name, u.id)) throw new ServiceError("That name is already used.");
        c.name = u.name = name;
      }
      if (patch.password) {
        u.salt = uid();
        u.hash = await hashPassword(patch.password, u.salt);
      }
      save(db);
      return { ...c };
    },
    async deleteClient(token, id) {
      const db = load();
      advisor(db, token);
      const fundIds = new Set(db.funds.filter((f) => f.clientId === id).map((f) => f.id));
      removeDocs(db, new Set(db.documents.filter((d) => fundIds.has(d.fundId)).map((d) => d.id)));
      db.funds = db.funds.filter((f) => f.clientId !== id);
      const userIds = new Set(db.users.filter((u) => u.clientId === id).map((u) => u.id));
      db.users = db.users.filter((u) => !userIds.has(u.id));
      for (const [t, uidv] of Object.entries(db.sessions)) if (userIds.has(uidv)) delete db.sessions[t];
      db.clients = db.clients.filter((c) => c.id !== id);
      save(db);
    },

    async createFund(token, clientId, name) {
      const db = load();
      advisor(db, token);
      if (!db.clients.some((c) => c.id === clientId)) throw new ServiceError("Client not found.");
      if (!name.trim()) throw new ServiceError("Fund name is required.");
      const f: Fund = { id: uid(), clientId, name: name.trim() };
      db.funds.push(f);
      save(db);
      return f;
    },
    async updateFund(token, fundId, name) {
      const db = load();
      advisor(db, token);
      const f = fund(db, fundId);
      if (!name.trim()) throw new ServiceError("Fund name is required.");
      f.name = name.trim();
      save(db);
      return { ...f };
    },
    async deleteFund(token, fundId) {
      const db = load();
      advisor(db, token);
      fund(db, fundId);
      removeDocs(db, new Set(db.documents.filter((d) => d.fundId === fundId).map((d) => d.id)));
      db.funds = db.funds.filter((f) => f.id !== fundId);
      save(db);
    },

    async createDocument(token, fundId, input) {
      const db = load();
      advisor(db, token);
      fund(db, fundId);
      const row: DocRow = { id: uid(), fundId, createdAt: new Date().toISOString(), data: validateDoc(input), paid: false };
      db.documents.push(row);
      save(db);
      return view(row);
    },
    async updateDocument(token, documentId, input) {
      const db = load();
      advisor(db, token);
      const d = doc(db, documentId);
      d.data = validateDoc(input);
      save(db);
      return view(d);
    },
    async deleteDocument(token, documentId) {
      const db = load();
      advisor(db, token);
      doc(db, documentId);
      removeDocs(db, new Set([documentId]));
      save(db);
    },
    async setPaid(token, documentId, paid) {
      const db = load();
      advisor(db, token);
      const d = doc(db, documentId);
      if (d.data.kind !== "capital_call") throw new ServiceError("Only capital calls can be paid.");
      d.paid = paid;
      save(db);
    },
    async setChecked(token, documentId, checked) {
      const db = load();
      const u = userFor(db, token);
      if (u.role !== "client" || !u.clientId) throw new ServiceError("Only a client can do that.");
      const d = doc(db, documentId);
      if (fund(db, d.fundId).clientId !== u.clientId) throw new ServiceError("Document not found.");
      const key = `${u.clientId}:${documentId}`;
      db.checks = db.checks.filter((c) => c !== key);
      if (checked) db.checks.push(key);
      save(db);
    },

    async getClientOverview(token, clientId): Promise<ClientOverview> {
      const db = load();
      const u = userFor(db, token);
      if (u.role === "client" && u.clientId !== clientId) throw new ServiceError("Client not found.");
      const client = db.clients.find((c) => c.id === clientId);
      if (!client) throw new ServiceError("Client not found.");
      const funds = db.funds
        .filter((f) => f.clientId === clientId)
        .sort((a, b) => a.name.localeCompare(b.name))
        .map((f) => ({
          ...f,
          documents: db.documents
            .filter((d) => d.fundId === f.id)
            .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
            .map((d) => ({
              ...view(d),
              ...(u.role === "client" && d.data.kind === "capital_call"
                ? { checked: db.checks.includes(`${clientId}:${d.id}`) }
                : {}),
            })),
        }));
      const morning = funds
        .flatMap((f) =>
          f.documents.flatMap((d) =>
            d.kind === "capital_call" && !d.paid
              ? [{ documentId: d.id, fundId: f.id, fundName: f.name, title: d.title, amount: d.amount, dueDate: d.dueDate }]
              : [],
          ),
        )
        .sort((a, b) => a.dueDate.localeCompare(b.dueDate));
      return { client: { ...client }, morning, funds };
    },
  };
}

export function memoryKV(): KV {
  const m = new Map<string, string>();
  return { getItem: (k) => m.get(k) ?? null, setItem: (k, v) => void m.set(k, v) };
}
