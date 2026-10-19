import { beforeEach, describe, expect, it, vi } from "vitest";
import { createHttpService } from "./http";
import { ServiceError } from "./types";

const svc = createHttpService();

function jsonResponse(body: unknown, status = 200) {
  return new Response(body === undefined ? "" : JSON.stringify(body), { status });
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

describe("http service", () => {
  it("signs in against the API and keeps the bearer token on later calls", async () => {
    const fetchMock = vi.mocked(fetch);
    fetchMock.mockResolvedValueOnce(jsonResponse({ token: "tok", role: "advisor", name: "Ada" }));
    fetchMock.mockResolvedValueOnce(jsonResponse([{ id: "c1", name: "Bea" }]));

    const session = await svc.login("Ada", "password");
    await svc.listClients(session.token);

    expect(fetchMock).toHaveBeenNthCalledWith(1, "http://127.0.0.1:8000/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: "Ada", password: "password" }),
    });
    expect(fetchMock).toHaveBeenNthCalledWith(2, "http://127.0.0.1:8000/clients", {
      method: "GET",
      headers: { Authorization: "Bearer tok" },
      body: undefined,
    });
  });

  it("surfaces the API error text", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse({ detail: "Wrong name or password." }, 401));
    await expect(svc.login("Ada", "nope")).rejects.toThrow(new ServiceError("Wrong name or password."));
  });

  it("treats an empty session response as signed out", async () => {
    vi.mocked(fetch).mockResolvedValueOnce(jsonResponse(null));
    await expect(svc.getSession("gone")).resolves.toBeNull();
  });
});
