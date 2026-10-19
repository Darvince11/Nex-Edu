"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { type Arm, api, getSelectedSchool, type Me, type Subject, type Term } from "./api";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<Me>("/api/v1/me"),
    staleTime: 60_000,
  });
}

/** The selected school's slug (read after mount, since it lives in a cookie). */
export function useSchoolSlug(): string | undefined | null {
  const [slug, setSlug] = useState<string | undefined | null>(null); // null = not read yet
  useEffect(() => setSlug(getSelectedSchool()), []);
  return slug;
}

export function useSchool() {
  const me = useMe();
  const slug = useSchoolSlug();
  const school = me.data?.schools.find((s) => s.slug === slug);
  return { me, slug, school, roles: school?.roles ?? [] };
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

export function useArms(mine = false) {
  return useQuery({
    queryKey: ["arms", mine],
    queryFn: () => api.get<Arm[]>(`/api/v1/academics/arms${mine ? "?mine=1" : ""}`),
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
