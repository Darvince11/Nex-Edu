"use client";

import { useQuery } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";
import {
  type Arm,
  api,
  fetchImage,
  getSelectedSchool,
  type Me,
  type MySchool,
  type Subject,
  selectSchool,
  type Term,
} from "./api";
import { canAny, type Permission } from "./permissions";
import { pickSchool } from "./school";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/api/v1/me"),
    staleTime: 60_000,
  });
}

export type SchoolSession = {
  me: ReturnType<typeof useMe>;
  slug: string | undefined;
  school: MySchool | undefined;
  roles: string[];
  permissions: string[];
  can: (...wanted: Permission[]) => boolean;
  /** Is this module switched on for the school? Core modules always are. */
  hasModule: (code: string) => boolean;
};

/**
 * Works out the person's school (see pickSchool) and remembers it for API calls.
 * Only the school layout calls this; pages read the result with useSchool().
 * `school` stays undefined until the cookie is set, so no request goes out
 * without the right school.
 */
export function useResolveSchool(): SchoolSession & { resolving: boolean } {
  const me = useMe();
  const [saved, setSaved] = useState<string | undefined | null>(null); // null = cookie not read yet
  useEffect(() => setSaved(getSelectedSchool()), []);
  const resolved = me.data && saved !== null ? pickSchool(me.data, saved) : undefined;
  useEffect(() => {
    if (resolved && resolved !== saved) {
      selectSchool(resolved);
      setSaved(resolved);
    }
  }, [resolved, saved]);
  const school =
    resolved && resolved === saved ? me.data?.schools.find((s) => s.slug === resolved) : undefined;
  const permissions = school?.permissions ?? [];
  return {
    me,
    slug: school?.slug,
    school,
    roles: school?.roles ?? [],
    permissions,
    can: (...wanted) => canAny(permissions, ...wanted),
    hasModule: (code) => Boolean(school?.modules.includes(code)),
    resolving: me.isPending || saved === null || (Boolean(resolved) && resolved !== saved),
  };
}

export const SchoolContext = createContext<SchoolSession | null>(null);

/** The signed-in person's school, roles and permissions (inside the school layout). */
export function useSchool(): SchoolSession {
  const session = useContext(SchoolContext);
  if (!session) throw new Error("useSchool() is only available inside the school layout.");
  return session;
}

export function useTerms() {
  return useQuery({ queryKey: ["terms"], queryFn: () => api.get<Term[]>("/api/v1/academics/terms") });
}

export function useCurrentTerm() {
  return useQuery({
    queryKey: ["terms", "current"],
    queryFn: () => api.get<Term | null>("/api/v1/academics/terms/current"),
  });
}

/** Classes: all of them, the ones I teach (`true`), or the ones I'm class teacher of ("form"). */
export function useArms(mine: boolean | "form" = false, enabled = true) {
  const query = mine === "form" ? "?mine=form" : mine ? "?mine=1" : "";
  return useQuery({
    queryKey: ["arms", mine],
    queryFn: () => api.get<Arm[]>(`/api/v1/academics/arms${query}`),
    enabled,
  });
}

export function useSubjects(arm?: string) {
  return useQuery({
    queryKey: ["subjects", arm ?? "all"],
    queryFn: () => api.get<Subject[]>(`/api/v1/academics/subjects${arm ? `?arm=${arm}` : ""}`),
  });
}

/** Tracks navigator.onLine so screens can say "you're offline". */
export function useOnline(): boolean {
  const [online, setOnline] = useState(true);
  useEffect(() => {
    const update = () => setOnline(navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);
  return online;
}

export const SCHOOL_LOGO = "/api/v1/school/logo";
export const PUBLIC_SCHOOL_LOGO = "/api/v1/public/school-logo";

/**
 * A school's logo as a local object URL (allowed by the CSP's img-src blob:),
 * or null when the school hasn't uploaded one. Freed when it changes.
 */
export function useSchoolLogo(path: string, school: string | undefined, enabled = Boolean(school)) {
  const logo = useQuery({
    queryKey: ["school-logo", path, school ?? ""],
    queryFn: () => fetchImage(path, school),
    enabled,
    staleTime: 5 * 60_000,
    retry: false,
  });
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!logo.data) {
      setUrl(null);
      return;
    }
    const objectUrl = URL.createObjectURL(logo.data);
    setUrl(objectUrl);
    return () => URL.revokeObjectURL(objectUrl);
  }, [logo.data]);
  return url;
}
