"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { SearchResponse } from "@/lib/types";

export function useResearch() {
  const [connection, setConnection] = useState("Checking API");
  const [result, setResult] = useState<SearchResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    api
      .health(AbortSignal.any([controller.signal, AbortSignal.timeout(5000)]))
      .then(() => setConnection("API connected"))
      .catch(() => {
        if (!controller.signal.aborted) setConnection("API offline");
      });
    return () => {
      controller.abort();
      activeRequest.current?.abort();
    };
  }, []);

  const search = useCallback(async (query: string) => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const data = await api.search(
        query,
        AbortSignal.any([controller.signal, AbortSignal.timeout(35000)]),
      );
      if (!controller.signal.aborted) {
        setResult(data);
        setConnection("API connected");
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        setError(error instanceof Error ? error.message : "Search failed.");
        if (error instanceof ApiError && error.status === 0) {
          setConnection("API offline");
        }
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  const clearSearch = useCallback(() => {
    activeRequest.current?.abort();
    setResult(null);
    setLoading(false);
    setError(null);
  }, []);

  return { connection, result, loading, error, search, clearSearch };
}
