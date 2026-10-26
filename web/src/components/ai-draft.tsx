"use client";

import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { Button, ErrorText, Field, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { useSchool } from "@/lib/hooks";
import { PERM } from "@/lib/permissions";

/** AI drafting help is on for the school and this person may ask for drafts. */
export function useCanDraft(): boolean {
  const { can, hasModule } = useSchool();
  return hasModule("ai_assist") && can(PERM.AI_DRAFT);
}

const NOTE = "A draft to read and change before you save. Pupils' names are never sent.";

/** "Draft with AI" for one report-card comment box. */
export function CommentDraftButton({
  reportCard,
  forHead,
  onDraft,
}: {
  reportCard: string;
  forHead: boolean;
  onDraft: (text: string) => void;
}) {
  const draft = useMutation({
    mutationFn: () =>
      api.post<{ draft: string }>("/api/v1/assist/report-comment", {
        report_card: reportCard,
        for_head: forHead,
      }),
    onSuccess: (data) => onDraft(data.draft),
  });
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="ghost"
        busy={draft.isPending}
        onClick={() => draft.mutate()}
        aria-label={
          forHead ? "Draft the head teacher's comment with AI" : "Draft the class teacher's comment with AI"
        }
      >
        Draft with AI
      </Button>
      {draft.isSuccess && <span className="text-xs text-neutral-600 dark:text-neutral-400">{NOTE}</span>}
      <ErrorText error={draft.error} />
    </div>
  );
}

/** Rough notes in, a draft announcement out (title and message), for the person to edit. */
export function AnnouncementDrafter({ onDraft }: { onDraft: (title: string, body: string) => void }) {
  const [open, setOpen] = useState(false);
  const [notes, setNotes] = useState("");
  const draft = useMutation({
    mutationFn: () => api.post<{ title: string; body: string }>("/api/v1/assist/announcement", { notes }),
    onSuccess: (data) => {
      onDraft(data.title, data.body);
      setOpen(false);
    },
  });
  if (!open)
    return (
      <div>
        <Button type="button" variant="ghost" onClick={() => setOpen(true)}>
          Draft from notes with AI
        </Button>
        {draft.isSuccess && <p className="text-xs text-neutral-600 dark:text-neutral-400">{NOTE}</p>}
      </div>
    );
  return (
    <div className="flex flex-col gap-2 rounded-control border border-neutral-200 p-3 dark:border-neutral-800">
      <Field label="Your notes" hint="What, when, where, what parents should do. Short phrases are fine.">
        <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={3} maxLength={2000} />
      </Field>
      <ErrorText error={draft.error} />
      <div className="flex gap-2">
        <Button
          type="button"
          variant="secondary"
          busy={draft.isPending}
          disabled={!notes.trim()}
          onClick={() => draft.mutate()}
        >
          Write the draft
        </Button>
        <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}
