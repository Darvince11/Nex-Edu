/** Online lesson and meeting links: any service works; Nex Edu only names it. */

const SERVICES: [string, string][] = [
  ["meet.google.com", "Google Meet"],
  ["zoom.us", "Zoom"],
  ["teams.microsoft.com", "Microsoft Teams"],
  ["teams.live.com", "Microsoft Teams"],
  ["chat.whatsapp.com", "WhatsApp"],
  ["call.whatsapp.com", "WhatsApp"],
  ["wa.me", "WhatsApp"],
  ["youtube.com", "YouTube"],
  ["youtu.be", "YouTube"],
];

export function videoService(url: string): string {
  try {
    const host = new URL(url).hostname.toLowerCase();
    const match = SERVICES.find(([domain]) => host === domain || host.endsWith(`.${domain}`));
    return match ? match[1] : "";
  } catch {
    return "";
  }
}

/** "Join on Zoom" as a link that opens in a new tab. Renders nothing without a safe https link. */
export function JoinLink({ url, label = "Join" }: { url?: string | null; label?: string }) {
  if (!url?.startsWith("https://")) return null;
  const service = videoService(url);
  return (
    <a
      href={url}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-sm font-medium text-link underline hover:text-link-hover"
    >
      {service ? `${label} on ${service}` : `${label} online`}
      <span className="sr-only"> (opens in a new tab)</span>
    </a>
  );
}
