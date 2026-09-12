"use client";

import { useEffect, useState, useRef, useCallback } from "react";

/**
 * Hook de debouncing réactif pour éviter les requêtes excessives lors de la saisie utilisateur.
 */
export function useDebounce<T>(value: T, delayMs: number = 300): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedValue(value);
    }, delayMs);

    return () => {
      clearTimeout(timer);
    };
  }, [value, delayMs]);

  return debouncedValue;
}

/**
 * Hook de throttling pour limiter la cadence d'exécution d'événements rapides (scroll, resize, métriques).
 */
export function useThrottle<T>(value: T, limitMs: number = 300): T {
  const [throttledValue, setThrottledValue] = useState<T>(value);
  const lastRan = useRef(Date.now());

  useEffect(() => {
    const handler = setTimeout(() => {
      if (Date.now() - lastRan.current >= limitMs) {
        setThrottledValue(value);
        lastRan.current = Date.now();
      }
    }, limitMs - (Date.now() - lastRan.current));

    return () => {
      clearTimeout(handler);
    };
  }, [value, limitMs]);

  return throttledValue;
}

/**
 * Gestionnaire de déduplication des requêtes en vol (Inflight Request Deduplication).
 * Évite de lancer plusieurs requêtes HTTP identiques simultanées.
 */
class RequestDeduplicator {
  private inflight = new Map<string, Promise<any>>();

  async execute<T>(key: string, fetcher: () => Promise<T>): Promise<T> {
    const existing = this.inflight.get(key);
    if (existing) {
      return existing as Promise<T>;
    }

    const promise = fetcher()
      .then((data) => {
        this.inflight.delete(key);
        return data;
      })
      .catch((err) => {
        this.inflight.delete(key);
        throw err;
      });

    this.inflight.set(key, promise);
    return promise;
  }
}

export const requestDeduplicator = new RequestDeduplicator();

/**
 * Cache client mémoire à expiration glissante avec TTL.
 */
interface ClientCacheEntry<T> {
  data: T;
  expiresAt: number;
}

class ClientMemoryCache {
  private cache = new Map<string, ClientCacheEntry<any>>();

  get<T>(key: string): T | null {
    const entry = this.cache.get(key);
    if (!entry) return null;
    if (Date.now() > entry.expiresAt) {
      this.cache.delete(key);
      return null;
    }
    return entry.data as T;
  }

  set<T>(key: string, data: T, ttlMs: number = 30000): void {
    this.cache.set(key, {
      data,
      expiresAt: Date.now() + ttlMs,
    });
  }

  invalidate(prefix?: string): void {
    if (!prefix) {
      this.cache.clear();
      return;
    }
    for (const key of this.cache.keys()) {
      if (key.startsWith(prefix)) {
        this.cache.delete(key);
      }
    }
  }
}

export const clientCache = new ClientMemoryCache();

/**
 * Fetcher optimisé combinant déduplication et cache client avec TTL.
 */
export async function cachedFetch<T>(
  url: string,
  options?: RequestInit,
  ttlMs: number = 30000
): Promise<T> {
  const cacheKey = `${options?.method || "GET"}:${url}`;
  
  if (!options?.method || options.method === "GET") {
    const cached = clientCache.get<T>(cacheKey);
    if (cached !== null) {
      return cached;
    }
  }

  return requestDeduplicator.execute(cacheKey, async () => {
    const response = await fetch(url, options);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    if (!options?.method || options.method === "GET") {
      clientCache.set(cacheKey, data, ttlMs);
    }
    return data;
  });
}
