import { useEffect, useState } from "react";

export type Loadable<T> = { state: "loading" } | { state: "missing" } | { state: "ready"; data: T };

/** Fetch a pipeline artifact from public/data. Missing files are a legitimate
 *  state (pipeline hasn't produced them yet), not an error. */
export function useArtifact<T>(name: string): Loadable<T> {
  const [result, setResult] = useState<Loadable<T>>({ state: "loading" });
  useEffect(() => {
    let cancelled = false;
    fetch(`${import.meta.env.BASE_URL}data/${name}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(String(res.status)))))
      .then((data: T) => !cancelled && setResult({ state: "ready", data }))
      .catch(() => !cancelled && setResult({ state: "missing" }));
    return () => {
      cancelled = true;
    };
  }, [name]);
  return result;
}
