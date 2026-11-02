/** A deterministic in-memory localStorage (the host runtime's may be missing or experimental). */
export class MemStorage {
  #data = new Map<string, string>();
  getItem(key: string): string | null {
    return this.#data.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.#data.set(key, value);
  }
  removeItem(key: string): void {
    this.#data.delete(key);
  }
  clear(): void {
    this.#data.clear();
  }
}

Object.defineProperty(window, "localStorage", { value: new MemStorage(), configurable: true });
