/** Read the session token once from the query string and remove it from the visible URL. */
export function takeToken(loc: Location, history: History): string | null {
  const params = new URLSearchParams(loc.search);
  const token = params.get("token");
  if (token === null) return null;
  params.delete("token");
  const query = params.toString();
  history.replaceState(null, "", `${loc.pathname}${query === "" ? "" : `?${query}`}${loc.hash}`);
  return token === "" ? null : token;
}
