"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { Loading } from "@/components/ui";
import { useSchool } from "@/lib/hooks";

/** The school's Nex Edu subscription lives on the proprietor's account page, which
 * also works while the school is suspended. */
export default function SubscriptionPage() {
  const router = useRouter();
  const { slug } = useSchool();
  useEffect(() => {
    if (slug) router.replace(`/account/billing?school=${encodeURIComponent(slug)}`);
  }, [slug, router]);
  return <Loading />;
}
