#!/usr/bin/env python3
"""The copy rules that are cheaper to enforce than to ask for.

Every rule here was first written into a prompt, and the prompt was obeyed
most of the time, which is the problem: a rule obeyed most of the time ships
the exceptions. So each one is checked after the model answers, and a miss
costs a retry instead of a post.

Two kinds of problem, and the difference matters:

* **hard** - unambiguous and always wrong. A banned phrase, an explain with no
  number in it, two slides opening with the same word. Never accepted.
* **soft** - a judgement call measured by a crude proxy. Reading level is the
  only one: the Flesch-Kincaid formula was fitted to prose, not to four-line
  Instagram copy, so it is right about the direction and unreliable about the
  exact grade. Accepted on the last attempt rather than dropping the post back
  to the template copy, which is longer and blander than anything the model
  returns.

Items 26, 33, 34, 35 and 37 of instagram-backlog.md.
"""
import re

# Item 35. Phrases that mark copy as written by a model rather than by someone
# with something to say. Each one is a sentence the reader skips, which at four
# slides means a quarter of the post is skipped.
BANNED_PHRASES = [
    "in today's market", "in todays market", "in today's world",
    "it's important to note", "its important to note", "it is important to",
    "let's dive in", "lets dive in", "let's break it down", "dive deeper",
    "game changer", "game-changer", "at the end of the day",
    "the bottom line is", "when it comes to", "needless to say",
    "it's worth noting", "its worth noting", "in a nutshell",
    "that being said", "first and foremost", "the key takeaway is",
    "navigate the market", "in the ever-changing", "ever-evolving",
    "unlock the", "supercharge", "revolutionize", "revolutionise",
    # Hedges. The account teaches; a sentence that hedges teaches nothing.
    "may or may not", "it depends on your", "do your own research",
    "there are many factors",
]

# Item 37. A post whose hook opens with the same word as the last few posts
# reads, in a grid, as the same post four times. Checked against the hooks
# actually queued rather than against a fixed list.
_STOPWORDS_AT_START = {"the", "a", "an", "this", "that", "your", "you"}

_SENTENCE_SPLIT = re.compile(r"[.!?]+\s+|[.!?]+$")
_WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
_HAS_DIGIT = re.compile(r"\d")

# Item 26. "A $50 stock earning $2 a share" beats any restatement of the
# definition, so the explain slide must carry a real quantity.
#
# Spelled-out counting words used to pass this check, and on 4.10.2026 that
# turned out to be the hole: "the same three forces are lining up again" is
# not a quantity, it is a gesture at one, and it sailed through a gate whose
# whole purpose was to force a figure onto the card. Only two things count
# now: a digit, and the magnitude words that are genuinely quantitative on
# their own.
_SPELLED_NUMBERS = re.compile(
    r"\b(hundred|thousand|million|billion|trillion|half|double|triple|"
    r"quadrupled|tripled|doubled|halved)\b",
    re.IGNORECASE,
)


def banned_phrases(text):
    """Every banned phrase present in text, lowercased."""
    low = text.lower()
    return [p for p in BANNED_PHRASES if p in low]


def has_quantity(text):
    """Item 26: a digit, or a number written out in words."""
    return bool(_HAS_DIGIT.search(text) or _SPELLED_NUMBERS.search(text))


def _syllables(word):
    """Crude syllable count: vowel groups, with a silent trailing 'e'.

    Wrong on a word here and there (every English syllable heuristic is), but
    stable enough across a 200-character paragraph for the grade level to mean
    something.
    """
    word = word.lower().strip("'’-")
    if not word:
        return 0
    groups = re.findall(r"[aeiouy]+", word)
    n = len(groups)
    if word.endswith("e") and not word.endswith(("le", "ee", "ye")) and n > 1:
        n -= 1
    return max(1, n)


def grade_level(text):
    """Flesch-Kincaid grade level, or None if there is too little text.

    Below about a dozen words the formula swings wildly on a single long word,
    so short copy is not graded at all rather than graded badly.
    """
    sentences = [s for s in _SENTENCE_SPLIT.split(text) if s.strip()]
    words = _WORD.findall(text)
    if len(words) < 12 or not sentences:
        return None
    syllables = sum(_syllables(w) for w in words)
    return (0.39 * (len(words) / len(sentences))
            + 11.8 * (syllables / len(words)) - 15.59)


# Item 33. Ninth grade is the ceiling: the audience has never owned a share,
# and a sentence they have to re-read is a sentence they scroll past.
MAX_GRADE = 9.0


def first_word(text):
    words = _WORD.findall(text)
    return words[0].lower() if words else ""


def opening_word(text):
    """The first word that carries meaning, for the variety check.

    "The Fed just..." and "The jobs report just..." are not the same opening,
    so an article or a pronoun is skipped and the next word is used.
    """
    for w in _WORD.findall(text):
        if w.lower() not in _STOPWORDS_AT_START:
            return w.lower()
    return first_word(text)


def repeated_shape(slides):
    """Item 34: two slides in one carousel built the same way.

    Two checks, both about shape rather than subject: the same opening word,
    and the same sentence count at the same length. Both are what makes a
    carousel read as one sentence repeated four times.
    """
    problems = []
    opens = {}
    for name, text in slides.items():
        # The meaningful opening, not the literal first word: two slides that
        # both start "A" are a coincidence, two that both start "Hibbett" are
        # the same slide written twice.
        w = opening_word(text)
        if not w:
            continue
        if w in opens:
            problems.append(
                f"{name} and {opens[w]} both open with \"{w}\""
            )
        else:
            opens[w] = name
    return problems


# Item 13. One carousel a week opens on a question the reader answers from
# their own life, because a comment from a non-follower is the cheapest real
# engagement signal there is. "Why do high rates make paychecks bigger?" is a
# question too, but nobody answers it in the comments: it asks for knowledge.
# The tell of the right kind is that it is addressed to the reader.
_TO_THE_READER = re.compile(r"\b(you|your|you'd|you're|you've|yours)\b", re.I)
_KNOWLEDGE_OPENERS = ("why ", "how does ", "how do ", "what is ", "what are ", "what's ")


def question_hook_problems(hook):
    hook = hook.strip()
    problems = []
    if not hook.endswith("?"):
        problems.append("this is the question-hook post: the hook must be a question ending in \"?\"")
    if not _TO_THE_READER.search(hook):
        problems.append("the question-hook must be addressed to the reader (you, your)")
    if hook.lower().startswith(_KNOWLEDGE_OPENERS):
        problems.append("the question-hook asks for knowledge; ask about the reader's own "
                        "choice, guess or experience instead")
    return problems


def check(copy, recent_openings=(), question_hook=False):
    """Every rule, over a finished copy dict.

    Returns (hard, soft): two lists of human-readable problems, written to be
    pasted straight into the retry prompt.
    """
    hard, soft = [], []

    prose_keys = ("hook", "explain", "takeaway", "question")
    for key in prose_keys:
        found = banned_phrases(copy.get(key, ""))
        if found:
            hard.append(
                f"{key} contains the banned phrase \"{found[0]}\" - "
                f"delete the phrase, do not rephrase around it"
            )

    # Item 25. One idea per card. "And also" is the tell: it is how a second
    # idea gets stapled onto a slide that was finished, and the reader pays
    # for it with the half-second they were going to give the first idea.
    for key in prose_keys:
        low = copy.get(key, "").lower()
        for tell in (" and also", ", and also", "and also,"):
            if tell.strip(", ") in low:
                hard.append(
                    f"{key} staples a second idea on with \"and also\" - keep "
                    f"the stronger idea and delete the other one"
                )
                break

    # Item 26, on the one slide whose job is to be concrete.
    if not has_quantity(copy.get("explain", "")):
        hard.append(
            "explain has no number in it - name a real quantity (a price, a "
            "percentage, a count), not a description of one"
        )

    # Item 34 / 37. Only the three slide-carrying fields: the question is a
    # sub-line under the takeaway rather than a slide of its own, and holding
    # it to the same no-repeat rule turned out to reject copy a reader would
    # never notice.
    hard += repeated_shape({k: copy.get(k, "") for k in ("hook", "explain", "takeaway")})
    opening = opening_word(copy.get("hook", ""))
    if opening and opening in {o for o in recent_openings if o}:
        hard.append(
            f"the hook opens on \"{opening}\", which the last posts already "
            f"used - open on a different word"
        )

    if question_hook:
        hard += question_hook_problems(copy.get("hook", ""))

    # Item 33, soft: the formula is directionally right and numerically rough.
    graded = " ".join(copy.get(k, "") for k in ("explain", "takeaway"))
    grade = grade_level(graded)
    if grade is not None and grade > MAX_GRADE:
        soft.append(
            f"the explain and takeaway read at a grade {grade:.1f} level, "
            f"limit is {MAX_GRADE:.0f} - shorter sentences and plainer words, "
            f"keep the number"
        )

    return hard, soft
