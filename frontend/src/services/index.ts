import { createHttpService } from "./http";
import type { ArchService } from "./types";

export * from "./types";

let instance: ArchService | null = null;

/** The single entry point for backend calls. */
export function getService(): ArchService {
  if (!instance) instance = createHttpService();
  return instance;
}
