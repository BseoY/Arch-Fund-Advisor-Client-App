import { createMockService, memoryKV } from "./mock";
import type { ArchService } from "./types";

export * from "./types";

let instance: ArchService | null = null;

/**
 * The single entry point for backend calls. Swap the mock for a real
 * HTTP implementation of ArchService here; nothing else needs to change.
 */
export function getService(): ArchService {
  if (!instance) {
    const kv = typeof window !== "undefined" ? window.localStorage : memoryKV();
    instance = createMockService(kv);
  }
  return instance;
}
