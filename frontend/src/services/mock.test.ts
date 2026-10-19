import { beforeEach, describe, expect, it } from "vitest";
import { createMockService, memoryKV, type KV } from "./mock";
import type { ArchService } from "./types";

let kv: KV;
let svc: ArchService;
let adv: string;

beforeEach(async () => {
  kv = memoryKV();
  svc = createMockService(kv);
  adv = (await svc.setupAdvisor("Ada", "pw")).token;
});

const call = (title: string, amount: number, dueDate: string) =>
  ({ kind: "capital_call", title, amount, dueDate }) as const;

describe("morning view", () => {
  it("lists unpaid calls soonest due first with fund name and amount", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    const f1 = await svc.createFund(adv, c.id, "Fund A");
    const f2 = await svc.createFund(adv, c.id, "Fund B");
    await svc.createDocument(adv, f1.id, call("Q3", 500, "2026-12-01"));
    await svc.createDocument(adv, f2.id, call("Q2", 250, "2026-11-01"));
    await svc.createDocument(adv, f1.id, { kind: "investor_letter", title: "L", summary: "New GP" });
    const o = await svc.getClientOverview(adv, c.id);
    expect(o.morning.map((m) => [m.fundName, m.amount, m.dueDate])).toEqual([
      ["Fund B", 250, "2026-11-01"],
      ["Fund A", 500, "2026-12-01"],
    ]);
  });

  it("marking paid removes from morning view but keeps it on the fund; unpaid restores it", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    const f = await svc.createFund(adv, c.id, "Fund A");
    const d = await svc.createDocument(adv, f.id, call("Q3", 500, "2026-12-01"));
    await svc.setPaid(adv, d.id, true);
    let o = await svc.getClientOverview(adv, c.id);
    expect(o.morning).toHaveLength(0);
    expect(o.funds[0].documents[0].paid).toBe(true);
    await svc.setPaid(adv, d.id, false);
    o = await svc.getClientOverview(adv, c.id);
    expect(o.morning).toHaveLength(1);
  });

  it("only the advisor can change paid status", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    const f = await svc.createFund(adv, c.id, "F");
    const d = await svc.createDocument(adv, f.id, call("Q", 1, "2026-01-01"));
    const bea = (await svc.login("Bea", "pw")).token;
    await expect(svc.setPaid(bea, d.id, true)).rejects.toThrow();
  });
});

describe("persistence", () => {
  it("data survives a restart", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    await svc.createFund(adv, c.id, "Fund A");
    const restarted = createMockService(kv);
    const token = (await restarted.login("Ada", "pw")).token;
    const o = await restarted.getClientOverview(token, c.id);
    expect(o.funds.map((f) => f.name)).toEqual(["Fund A"]);
  });

  it("does not store plain passwords", async () => {
    await svc.createClient(adv, "Bea", "secret-pass");
    expect(kv.getItem("arch-morning-view-db-v1")).not.toContain("secret-pass");
  });
});

describe("client separation", () => {
  it("a client cannot read another client's funds", async () => {
    const a = await svc.createClient(adv, "Bea", "pw");
    const b = await svc.createClient(adv, "Cal", "pw");
    await svc.createFund(adv, b.id, "Cal Fund");
    const bea = (await svc.login("Bea", "pw")).token;
    await expect(svc.getClientOverview(bea, b.id)).rejects.toThrow();
    const own = await svc.getClientOverview(bea, a.id);
    expect(own.funds).toHaveLength(0);
  });

  it("a client cannot tick another client's document", async () => {
    await svc.createClient(adv, "Bea", "pw");
    const b = await svc.createClient(adv, "Cal", "pw");
    const f = await svc.createFund(adv, b.id, "Cal Fund");
    const d = await svc.createDocument(adv, f.id, call("Q", 1, "2026-01-01"));
    const bea = (await svc.login("Bea", "pw")).token;
    await expect(svc.setChecked(bea, d.id, true)).rejects.toThrow();
  });

  it("client checkmark is saved, hidden from advisor, and does not change paid", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    const f = await svc.createFund(adv, c.id, "F");
    const d = await svc.createDocument(adv, f.id, call("Q", 1, "2026-01-01"));
    const bea = (await svc.login("Bea", "pw")).token;
    await svc.setChecked(bea, d.id, true);
    const mine = await svc.getClientOverview(bea, c.id);
    expect(mine.funds[0].documents[0]).toMatchObject({ checked: true, paid: false });
    const advView = await svc.getClientOverview(adv, c.id);
    expect(advView.funds[0].documents[0].checked).toBeUndefined();
    expect(advView.morning).toHaveLength(1);
  });

  it("only the advisor can manage clients", async () => {
    await svc.createClient(adv, "Bea", "pw");
    const bea = (await svc.login("Bea", "pw")).token;
    await expect(svc.listClients(bea)).rejects.toThrow();
  });
});

describe("deletion", () => {
  it("deleting a client removes its login, funds and documents", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    const f = await svc.createFund(adv, c.id, "F");
    await svc.createDocument(adv, f.id, call("Q", 1, "2026-01-01"));
    await svc.deleteClient(adv, c.id);
    await expect(svc.login("Bea", "pw")).rejects.toThrow();
    const db = JSON.parse(kv.getItem("arch-morning-view-db-v1")!);
    expect(db.funds).toHaveLength(0);
    expect(db.documents).toHaveLength(0);
  });

  it("deleting a fund removes its documents", async () => {
    const c = await svc.createClient(adv, "Bea", "pw");
    const f = await svc.createFund(adv, c.id, "F");
    await svc.createDocument(adv, f.id, call("Q", 1, "2026-01-01"));
    await svc.deleteFund(adv, f.id);
    const o = await svc.getClientOverview(adv, c.id);
    expect(o.funds).toHaveLength(0);
    expect(o.morning).toHaveLength(0);
  });
});
