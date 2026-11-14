import { api } from "./api";
import type { Paper } from "./types";

function normalizedDoi(value: string) {
  return decodeURIComponent(value)
    .replace(/^https?:\/\/(?:dx\.)?doi\.org\//i, "")
    .toLowerCase();
}

export function isPaperLink(value: string) {
  return (
    /^https?:\/\//i.test(value) ||
    /^10\.\d{4,9}\//i.test(value) ||
    /^W\d+$/i.test(value)
  );
}

export async function resolvePaper(value: string): Promise<Paper> {
  const input = value.trim();
  if (/^W\d+$/i.test(input)) return api.paper(input.toUpperCase());

  let doi: string | null = /^10\.\d{4,9}\//i.test(input) ? input : null;
  let articleUrl: string | null = null;
  if (!doi) {
    let url: URL;
    try {
      url = new URL(input);
    } catch {
      throw new Error("Enter a valid article URL, DOI, or OpenAlex work ID.");
    }
    if (!["http:", "https:"].includes(url.protocol)) {
      throw new Error("Article links must use http or https.");
    }
    articleUrl = url.href;
    const workId =
      url.hostname.toLowerCase() === "openalex.org" &&
      url.pathname.match(/^\/(W\d+)\/?$/i)?.[1];
    if (workId) return api.paper(workId.toUpperCase());
    if (/^(?:dx\.)?doi\.org$/i.test(url.hostname)) {
      doi = url.pathname.slice(1);
    } else {
      const match = decodeURIComponent(url.pathname).match(
        /10\.\d{4,9}\/[^?#\s]+/i,
      );
      if (match) doi = match[0];
    }
  }

  const result = await api.search(doi ?? articleUrl ?? input);
  const paper = doi
    ? result.papers.find(
        (entry) =>
          entry.doi && normalizedDoi(entry.doi) === normalizedDoi(doi!),
      )
    : result.papers.find((entry) => entry.landing_page_url === articleUrl);
  if (!paper) {
    throw new Error(
      "We could not match that link to an indexed paper. Try its DOI or search by title.",
    );
  }
  return paper;
}
