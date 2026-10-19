export type Role = "advisor" | "client";

export interface Session {
  token: string;
  role: Role;
  name: string;
  /** Set when role === "client". */
  clientId?: string;
}

export interface Client {
  id: string;
  name: string;
}

export interface Fund {
  id: string;
  clientId: string;
  name: string;
}

export type DocumentInput =
  | { kind: "capital_call"; title: string; amount: number; dueDate: string }
  | { kind: "investor_letter"; title: string; summary: string };

export type FundDocument = DocumentInput & {
  id: string;
  fundId: string;
  createdAt: string;
  /** Only meaningful for capital calls. */
  paid?: boolean;
  /** The client's private checkmark. Only returned to that client. */
  checked?: boolean;
};

export interface MorningItem {
  documentId: string;
  fundId: string;
  fundName: string;
  title: string;
  amount: number;
  dueDate: string;
}

export interface ClientOverview {
  client: Client;
  morning: MorningItem[];
  funds: (Fund & { documents: FundDocument[] })[];
}

/**
 * Every backend call in the app goes through this interface.
 * Every method takes the caller's session token; the implementation
 * decides what that caller may see or change.
 */
export interface ArchService {
  hasAdvisor(): Promise<boolean>;
  setupAdvisor(name: string, password: string): Promise<Session>;
  login(name: string, password: string): Promise<Session>;
  getSession(token: string): Promise<Session | null>;
  logout(token: string): Promise<void>;

  listClients(token: string): Promise<Client[]>;
  createClient(token: string, name: string, password: string): Promise<Client>;
  updateClient(token: string, id: string, patch: { name?: string; password?: string }): Promise<Client>;
  deleteClient(token: string, id: string): Promise<void>;

  createFund(token: string, clientId: string, name: string): Promise<Fund>;
  updateFund(token: string, fundId: string, name: string): Promise<Fund>;
  deleteFund(token: string, fundId: string): Promise<void>;

  createDocument(token: string, fundId: string, input: DocumentInput): Promise<FundDocument>;
  updateDocument(token: string, documentId: string, input: DocumentInput): Promise<FundDocument>;
  deleteDocument(token: string, documentId: string): Promise<void>;
  setPaid(token: string, documentId: string, paid: boolean): Promise<void>;
  setChecked(token: string, documentId: string, checked: boolean): Promise<void>;

  getClientOverview(token: string, clientId: string): Promise<ClientOverview>;
}

export class ServiceError extends Error {}
