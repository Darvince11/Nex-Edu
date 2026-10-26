"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Alert, Button, Card, ErrorText, Input } from "@/components/ui";
import { api, apiFetch } from "@/lib/api";
import { formatDate, timeAgo } from "@/lib/format";

type Feed = { active: boolean; created_at: string | null; last_used_at: string | null };

/** A private link that Google Calendar, Outlook or Apple Calendar subscribes to. */
export function CalendarLinkCard() {
  const client = useQueryClient();
  const [url, setUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const feed = useQuery({
    queryKey: ["calendar-feed"],
    queryFn: () => api.get<Feed>("/api/v1/calendar/feed"),
  });
  const issue = useMutation({
    mutationFn: () => api.post<{ url: string }>("/api/v1/calendar/feed"),
    onSuccess: (data) => {
      setUrl(data.url);
      setCopied(false);
      void client.invalidateQueries({ queryKey: ["calendar-feed"] });
    },
  });
  const off = useMutation({
    mutationFn: () => api.del("/api/v1/calendar/feed"),
    onSuccess: () => {
      setUrl(null);
      void client.invalidateQueries({ queryKey: ["calendar-feed"] });
    },
  });
  return (
    <Card title="Calendar on your phone">
      <p className="text-sm text-neutral-600 dark:text-neutral-300">
        Term dates, holidays, school events and your parent meetings in Google Calendar, Outlook or your
        phone's calendar. Keep the link to yourself: anyone with it can see your school calendar.
      </p>
      <ErrorText error={feed.error ?? issue.error ?? off.error} />
      {url ? (
        <div className="mt-3 flex flex-col gap-2">
          <label className="text-sm font-medium" htmlFor="calendar-link">
            Your calendar link (shown once)
          </label>
          <Input id="calendar-link" readOnly value={url} onFocus={(e) => e.currentTarget.select()} />
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              onClick={() => {
                void navigator.clipboard?.writeText(url).then(() => setCopied(true));
              }}
            >
              {copied ? "Copied" : "Copy link"}
            </Button>
          </div>
          <p className="text-xs text-neutral-600 dark:text-neutral-400">
            Google Calendar: Other calendars › From URL. Outlook: Add calendar › Subscribe from web. iPhone:
            Settings › Calendar › Accounts › Add subscribed calendar.
          </p>
        </div>
      ) : feed.data?.active ? (
        <p className="mt-3 text-sm">
          Your link is on
          {feed.data.last_used_at ? `; your calendar last checked it ${timeAgo(feed.data.last_used_at)}` : ""}
          . Made {formatDate(feed.data.created_at)}.
        </p>
      ) : null}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button variant="secondary" busy={issue.isPending} onClick={() => issue.mutate()}>
          {feed.data?.active ? "Make a new link" : "Get my calendar link"}
        </Button>
        {feed.data?.active && (
          <Button variant="ghost" busy={off.isPending} onClick={() => off.mutate()}>
            Turn the link off
          </Button>
        )}
      </div>
    </Card>
  );
}

type PushInfo = { enabled: boolean; public_key: string; browsers: number };

function keyBytes(base64: string): Uint8Array<ArrayBuffer> {
  const padded = `${base64}${"=".repeat((4 - (base64.length % 4)) % 4)}`
    .replace(/-/g, "+")
    .replace(/_/g, "/");
  return Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
}

/** Notifications on this device (browser push). Off until the person turns it on here. */
export function NotificationsCard() {
  const info = useQuery({
    queryKey: ["push"],
    queryFn: () => apiFetch<PushInfo>("/api/v1/push", { school: false }),
  });
  const [on, setOn] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const supported = typeof window !== "undefined" && "serviceWorker" in navigator && "PushManager" in window;

  useEffect(() => {
    if (!supported) return;
    void navigator.serviceWorker
      .getRegistration("/sw.js")
      .then((reg) => reg?.pushManager.getSubscription())
      .then((sub) => setOn(Boolean(sub)));
  }, [supported]);

  async function turnOn(publicKey: string) {
    const permission = await Notification.requestPermission();
    if (permission !== "granted")
      throw new Error("Notifications are blocked for Nex Edu in this browser's settings.");
    const reg = await navigator.serviceWorker.register("/sw.js");
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: keyBytes(publicKey),
    });
    const json = sub.toJSON();
    await apiFetch("/api/v1/push", {
      method: "POST",
      school: false,
      body: { endpoint: json.endpoint, p256dh: json.keys?.p256dh, auth: json.keys?.auth },
    });
  }

  async function turnOff() {
    const reg = await navigator.serviceWorker.getRegistration("/sw.js");
    const sub = await reg?.pushManager.getSubscription();
    if (sub) {
      await apiFetch(`/api/v1/push?endpoint=${encodeURIComponent(sub.endpoint)}`, {
        method: "DELETE",
        school: false,
      });
      await sub.unsubscribe();
    }
  }

  const toggle = async () => {
    setBusy(true);
    setError(null);
    try {
      if (on) await turnOff();
      else if (info.data) await turnOn(info.data.public_key);
      setOn(!on);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Notifications on this device">
      {!info.data ? (
        <ErrorText error={info.error} />
      ) : !info.data.enabled ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">Not available yet.</p>
      ) : !supported ? (
        <p className="text-sm text-neutral-600 dark:text-neutral-300">
          This browser can't show notifications.
        </p>
      ) : (
        <>
          <p className="text-sm text-neutral-600 dark:text-neutral-300">
            A short alert on this phone or computer whenever something arrives in your Nex Edu inbox.
          </p>
          {error ? (
            <div className="mt-2">
              <Alert tone="error">
                {error instanceof Error ? error.message : "Couldn't change notifications."}
              </Alert>
            </div>
          ) : null}
          <div className="mt-3">
            <Button variant="secondary" busy={busy} disabled={on === null} onClick={() => void toggle()}>
              {on ? "Turn off on this device" : "Turn on for this device"}
            </Button>
          </div>
        </>
      )}
    </Card>
  );
}
