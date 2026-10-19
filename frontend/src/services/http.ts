import { ServiceError, type ArchService, type Client, type ClientOverview, type DocumentInput, type Fund, type FundDocument, type Session } from "./types";

const API_URL = (import.meta.env.VITE_API_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

type RequestOptions = {
  method?: string;
  token?: string;
  body?: unknown;
};

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (options.token) headers.Authorization = `Bearer ${options.token}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? "GET",
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    });
  } catch {
    throw new ServiceError("The server is not reachable.");
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : response.statusText;
    throw new ServiceError(typeof detail === "string" ? detail : "Something went wrong.");
  }
  return data as T;
}

export function createHttpService(): ArchService {
  return {
    hasAdvisor: () => request<boolean>("/advisor"),
    setupAdvisor: (name, password) => request<Session>("/advisor", { method: "POST", body: { name, password } }),
    login: (name, password) => request<Session>("/login", { method: "POST", body: { name, password } }),
    getSession: (token) => request<Session | null>("/session", { token }),
    logout: (token) => request<void>("/logout", { method: "POST", token }),

    listClients: (token) => request<Client[]>("/clients", { token }),
    createClient: (token, name, password) => request<Client>("/clients", { method: "POST", token, body: { name, password } }),
    updateClient: (token, id, patch) => request<Client>(`/clients/${id}`, { method: "PATCH", token, body: patch }),
    deleteClient: (token, id) => request<void>(`/clients/${id}`, { method: "DELETE", token }),

    createFund: (token, clientId, name) =>
      request<Fund>(`/clients/${clientId}/funds`, { method: "POST", token, body: { name } }),
    updateFund: (token, fundId, name) => request<Fund>(`/funds/${fundId}`, { method: "PATCH", token, body: { name } }),
    deleteFund: (token, fundId) => request<void>(`/funds/${fundId}`, { method: "DELETE", token }),

    createDocument: (token, fundId, input) =>
      request<FundDocument>(`/funds/${fundId}/documents`, { method: "POST", token, body: input }),
    updateDocument: (token, documentId, input: DocumentInput) =>
      request<FundDocument>(`/documents/${documentId}`, { method: "PUT", token, body: input }),
    deleteDocument: (token, documentId) => request<void>(`/documents/${documentId}`, { method: "DELETE", token }),
    setPaid: (token, documentId, paid) =>
      request<void>(`/documents/${documentId}/paid`, { method: "PATCH", token, body: { paid } }),
    setChecked: (token, documentId, checked) =>
      request<void>(`/documents/${documentId}/checked`, { method: "PATCH", token, body: { checked } }),

    getClientOverview: (token, clientId) => request<ClientOverview>(`/clients/${clientId}`, { token }),
  };
}
