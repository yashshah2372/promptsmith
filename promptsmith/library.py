"""The prompt library: expert guidance for common requests, matched by keyword.

Each template is what a specialist would tell a writer before they start. The enhancer
folds the matching template and the user's profile into one finished prompt.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Template:
    id: str
    title: str
    keywords: tuple[str, ...]
    guidance: str


LIBRARY: tuple[Template, ...] = (
    Template(
        id="linkedin_post",
        title="LinkedIn post",
        keywords=("linkedin", "post", "announce", "launch", "milestone"),
        guidance=(
            "Open with a hook line that stands alone (no 'I'm excited to announce'). Tell one concrete "
            "story or result, not a list of adjectives. Short paragraphs of 1-2 lines. End with a question "
            "or a clear next step. At most 3 hashtags, at the end. Match the length the user asked for."
        ),
    ),
    Template(
        id="cold_email",
        title="Cold or outreach email",
        keywords=("email", "outreach", "cold", "pitch", "reach out", "follow up", "follow-up"),
        guidance=(
            "Subject line under 7 words. First line is about the recipient, not the sender. One specific "
            "reason for writing, one piece of proof, one low-effort ask. Under 120 words. No attachments "
            "mentioned in a first email."
        ),
    ),
    Template(
        id="instagram_caption",
        title="Instagram caption",
        keywords=("instagram", "caption", "reel", "ig "),
        guidance=(
            "First line must work before the 'more' cut-off. Conversational, in the brand voice. One call "
            "to action. 3-8 relevant hashtags on a separate line. Emojis only if the voice uses them."
        ),
    ),
    Template(
        id="product_description",
        title="Product or service description",
        keywords=("product", "description", "listing", "service page", "sales page", "offer"),
        guidance=(
            "Lead with the outcome the buyer gets, then how. Address the main objection of the target "
            "audience. Use concrete specifics (numbers, materials, timeframes). Close with what to do next."
        ),
    ),
    Template(
        id="blog_outline",
        title="Blog post or article",
        keywords=("blog", "article", "outline", "newsletter", "essay"),
        guidance=(
            "Give a working title and a one-sentence promise to the reader. Outline H2 sections, each with "
            "the single point it makes and one example. Include an intro hook and a conclusion with a takeaway."
        ),
    ),
    Template(
        id="general",
        title="General request",
        keywords=(),
        guidance=(
            "Make the goal, audience, tone, format and length explicit. Ask for one clear deliverable. "
            "If key facts are missing, tell the model to leave labelled placeholders rather than invent them."
        ),
    ),
)

_BY_ID = {t.id: t for t in LIBRARY}


def match(request: str) -> Template:
    """Pick the template whose keywords best match the request; fall back to 'general'."""
    text = " " + re.sub(r"\s+", " ", request.lower()) + " "
    best, best_hits = _BY_ID["general"], 0
    for t in LIBRARY:
        hits = sum(1 for k in t.keywords if k in text)
        if hits > best_hits:
            best, best_hits = t, hits
    return best


def get(template_id: str) -> Template | None:
    return _BY_ID.get(template_id)
