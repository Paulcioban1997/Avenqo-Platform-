import "@testing-library/jest-dom/vitest";

const storage = new Map<string, string>();
const localStorageMock = {
	getItem: (key: string) => storage.get(key) ?? null,
	setItem: (key: string, value: string) => storage.set(key, String(value)),
	removeItem: (key: string) => storage.delete(key),
	clear: () => storage.clear(),
	key: (index: number) => Array.from(storage.keys())[index] ?? null,
	get length() { return storage.size; },
};

Object.defineProperty(window, "localStorage", {
	configurable: true,
	value: localStorageMock,
});
