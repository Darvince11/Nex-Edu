"""AI drafting help (optional module ``ai_assist``, owner's decision 26 Oct 2026):
drafts that a teacher edits and saves themselves. Nothing is sent to anyone, and
nothing is saved, without a person.

Privacy (Act 843): a pupil's name never leaves Nex Edu. Report-card drafts get the
pupil's results and attendance with "[PUPIL]" in place of the name, and the first
name is put back here. In announcement notes, any pupil's or guardian's name the
school holds is swapped for a placeholder ("[NAME-1]") and restored in the draft.
No date of birth, contact, health or money detail is ever sent. Only counts and
token totals are logged, never the text.

Claude via the Anthropic API (``ANTHROPIC_API_KEY``). The DPIA must be updated
before this is switched on for real schools.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from django.conf import settings
from django.utils import timezone

from .models import DraftLog

logger = logging.getLogger(__name__)

MODEL = "claude-opus-5-5"
PUPIL = "[PUPIL]"


class DraftUnavailable(Exception):
    """A draft can't be made right now; the message is safe to show."""


def configured() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def check_quota(kind: str) -> None:
    start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
    used = DraftLog.objects.filter(created_at__gte=start).count()
    if used >= settings.AI_DRAFTS_PER_DAY:
        raise DraftUnavailable("The school has used today's drafts. Try again tomorrow.")


# --- Names out, names back ----------------------------------------------------------------


@dataclass
class Redactor:
    """Swaps known names for placeholders and back."""

    names: list[str]
    found: dict[str, str] = field(default_factory=dict)  # placeholder -> name

    def __post_init__(self) -> None:
        words = sorted({n for n in self.names if len(n) >= 3}, key=len, reverse=True)
        self._pattern = (
            re.compile(r"\b(" + "|".join(re.escape(w) for w in words) + r")\b", re.IGNORECASE)
            if words
            else None
        )

    def hide(self, text: str) -> str:
        if self._pattern is None:
            return text
        seen: dict[str, str] = {}

        def swap(match: re.Match[str]) -> str:
            word = match.group(0)
            key = word.lower()
            if key not in seen:
                seen[key] = f"[NAME-{len(seen) + 1}]"
                self.found[seen[key]] = word
            return seen[key]

        return self._pattern.sub(swap, text)

    def restore(self, text: str) -> str:
        for placeholder, name in self.found.items():
            text = text.replace(placeholder, name)
        return text


def school_names() -> list[str]:
    """Every pupil's and guardian's name parts the school holds."""
    from apps.students.models import Student, StudentGuardian

    names: list[str] = []
    for first, middle, last in Student.objects.values_list(
        "first_name", "middle_name", "last_name"
    ):
        names += [first, middle, last]
    for full in StudentGuardian.objects.values_list("full_name", flat=True):
        names += full.split()
    return [n.strip() for n in names if n and n.strip()]


# --- Talking to Claude --------------------------------------------------------------------


def _complete(*, system: str, prompt: str, kind: str, user_id: Any) -> str:
    import anthropic

    client = anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY, timeout=settings.AI_TIMEOUT_SECONDS, max_retries=2
    )
    log = DraftLog(kind=kind, user_id=user_id)
    try:
        response = client.beta.messages.create(
            model=MODEL,
            max_tokens=4000,
            # Short drafts: low effort is plenty and keeps them quick.
            output_config={"effort": "low"},
            # If a safety check declines, the API retries on a suitable model itself.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
    except anthropic.AuthenticationError:
        logger.error("AI drafting: the Anthropic API key was refused")
        raise DraftUnavailable("Drafting isn't set up correctly. Tell Nex Edu support.") from None
    except anthropic.PermissionDeniedError:
        logger.error("AI drafting: the Anthropic API key lacks permission")
        raise DraftUnavailable("Drafting isn't set up correctly. Tell Nex Edu support.") from None
    except anthropic.RateLimitError:
        raise DraftUnavailable("Drafting is busy. Try again in a minute.") from None
    except anthropic.BadRequestError as exc:
        logger.error("AI drafting: bad request (%s)", exc.message)
        raise DraftUnavailable("Couldn't make a draft. Write it yourself this time.") from None
    except anthropic.APIStatusError as exc:
        logger.warning("AI drafting: API error %s", exc.status_code)
        raise DraftUnavailable("Drafting isn't available right now. Try again later.") from None
    except anthropic.APIConnectionError:  # includes timeouts
        logger.warning("AI drafting: no connection to the API")
        raise DraftUnavailable("Drafting isn't available right now. Try again later.") from None
    usage = getattr(response, "usage", None)
    log.input_tokens = getattr(usage, "input_tokens", 0) or 0
    log.output_tokens = getattr(usage, "output_tokens", 0) or 0
    if response.stop_reason == "refusal":
        log.save()
        raise DraftUnavailable("Couldn't make a draft for this. Write it yourself this time.")
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    if not text:
        log.save()
        raise DraftUnavailable("Couldn't make a draft. Try again.")
    log.ok = True
    log.save()
    return text


REPORT_SYSTEM = (
    "You help teachers at a Ghanaian basic school (KG to JHS) write the comment on a pupil's "
    "end-of-term report card. Write in plain British English, warm but honest, and specific to "
    "the results and attendance given: name a strength and one thing to work on, and end with "
    "encouragement. Two or three sentences, under 300 characters. Refer to the pupil only as "
    f"{PUPIL} and use no he/she pronouns. Don't invent facts, subjects or events that aren't in "
    "the information. Reply with the comment only, as plain text."
)


def report_comment(card: Any, *, for_head: bool, notes: str, user_id: Any) -> str:
    """A draft comment for one report card (the pupil's name is never sent)."""
    check_quota(DraftLog.Kind.REPORT_COMMENT)
    lines = "\n".join(
        f"- {line.get('subject') or line.get('subject_name', 'Subject')}: "
        f"{line.get('total', '?')} ({line.get('grade', '')} {line.get('remark', '')})".rstrip()
        for line in card.lines
    )
    facts = [
        f"Class level: {card.arm.level.name}",
        f"Term: {card.term.get_number_display()}",
        f"Average score: {card.average}",
    ]
    if card.position:
        facts.append(f"Position: {card.position} of {card.class_size}")
    if card.aggregate:
        facts.append(f"Aggregate (best 6, lower is better): {card.aggregate}")
    if card.days_open:
        facts.append(f"Attendance: present {card.days_present} of {card.days_open} days")
    redactor = Redactor([card.student.first_name, card.student.middle_name, card.student.last_name])
    prompt = (
        (
            "Write the head teacher's comment.\n"
            if for_head
            else "Write the class teacher's comment.\n"
        )
        + "\n".join(facts)
        + f"\nSubjects:\n{lines or '- (no subjects)'}"
        + (f"\nThe teacher's own notes: {redactor.hide(notes)}" if notes.strip() else "")
    )
    text = _complete(
        system=REPORT_SYSTEM, prompt=prompt, kind=DraftLog.Kind.REPORT_COMMENT, user_id=user_id
    )
    text = redactor.restore(text).replace(PUPIL, card.student.first_name)
    return text[:500]


ANNOUNCEMENT_SYSTEM = (
    "You help staff at a Ghanaian basic school (KG to JHS) write announcements to parents. "
    "Turn the notes into a short, clear, friendly announcement in plain British English that a "
    "busy parent can read on a phone: what, when, where, and what parents need to do. Keep any "
    "placeholder such as [NAME-1] exactly as written. Don't add facts, dates, fees or times that "
    "aren't in the notes. Reply in exactly this form:\nTitle: <a title of up to 80 characters>\n\n"
    "<the announcement, up to 900 characters>"
)


def announcement(*, notes: str, audience: str, user_id: Any) -> dict[str, str]:
    check_quota(DraftLog.Kind.ANNOUNCEMENT)
    redactor = Redactor(school_names())
    text = _complete(
        system=ANNOUNCEMENT_SYSTEM,
        prompt=f"Audience: {audience}\nNotes:\n{redactor.hide(notes)}",
        kind=DraftLog.Kind.ANNOUNCEMENT,
        user_id=user_id,
    )
    text = redactor.restore(text)
    title, _, body = text.partition("\n")
    if title.lower().startswith("title:"):
        title = title[6:].strip()
    else:  # no title line: keep everything as the body
        title, body = "", text
    return {"title": title[:120], "body": body.strip()[:2000]}
