/** Helpers de rol RBAC de organización (alineado con backend). */
export type OrgRole = "admin" | "user" | "viewer" | "api_user";

export function normalizeOrgRole(role: string | null | undefined): OrgRole {
  const r = (role || "user").trim().toLowerCase();
  if (r === "admin" || r === "user" || r === "viewer" || r === "api_user") return r;
  return "user";
}

export function canMutateDossiers(role: string | null | undefined): boolean {
  const r = normalizeOrgRole(role);
  return r === "admin" || r === "user" || r === "api_user";
}

export function isViewer(role: string | null | undefined): boolean {
  return normalizeOrgRole(role) === "viewer";
}

export function isOrgAdmin(role: string | null | undefined): boolean {
  return normalizeOrgRole(role) === "admin";
}
