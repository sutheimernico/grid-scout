import { useEffect, useState } from "react";

/** "missing" is a legitimate state (the pipeline has not produced the file yet);
 *  "error" is not: the file exists but could not be read, which must not be
 *  dressed up as "not produced yet". */
export type Loadable<T> = { state: "loading" } | { state: "missing" } | { state: "error" } | { state: "ready"; data: T };

/** Fetch one JSON artifact and classify the outcome. 404 = missing; anything else
 *  that is not a readable JSON document (server error, corrupt body, network
 *  failure) = error. */
export async function readArtifact<T>(url: string, fetchFn: typeof fetch = fetch): Promise<Exclude<Loadable<T>, { state: "loading" }>> {
  let res: Response;
  try {
    res = await fetchFn(url);
  } catch {
    return { state: "error" };
  }
  if (res.status === 404) return { state: "missing" };
  if (!res.ok) return { state: "error" };
  // a dev server or SPA host answers a missing file with its index page and a 200
  if ((res.headers.get("content-type") ?? "").includes("text/html")) return { state: "missing" };
  try {
    return { state: "ready", data: (await res.json()) as T };
  } catch {
    return { state: "error" };
  }
}

/** Fetch a pipeline artifact from public/data. */
export function useArtifact<T>(name: string): Loadable<T> {
  const [result, setResult] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    let cancelled = false;
    readArtifact<T>(`${import.meta.env.BASE_URL}data/${name}`).then((r) => !cancelled && setResult(r));
    return () => {
      cancelled = true;
    };
  }, [name]);
  return result;
}
