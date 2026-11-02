"""Offline intent parser.

This is the rule-based layer that keeps the product usable with no AI service
reachable. It maps a transcript to an intent name plus entities. Anything it
cannot classify becomes `chat`, which is the only path that needs the network.

Deliberately boring regex, not a model: it has to behave identically whether the
command arrived by voice, by dashboard text box, or from the firmware.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

WORD_NUMBERS: dict[str, int] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15,
    "twenty": 20, "twenty five": 25, "thirty": 30, "forty": 40, "forty five": 45,
    "fifty": 50, "sixty": 60, "ninety": 90, "half": 30,
    "a": 1, "an": 1, "couple": 2,
}


@dataclass
class Intent:
    name: str
    entities: dict[str, Any] = field(default_factory=dict)
    confidence: float = 1.0
    reply: Optional[str] = None

    @property
    def is_local(self) -> bool:
        return self.name != "chat"


def _to_int(token: str) -> Optional[int]:
    token = token.strip().lower()
    if not token:
        return None
    if token.isdigit():
        return int(token)
    return WORD_NUMBERS.get(token)


_DURATION_RE = re.compile(
    r"(?P<value>\d+|[a-z]+(?:\s+[a-z]+)?)\s*"
    r"(?P<unit>hours?|hrs?|h|minutes?|mins?|m|seconds?|secs?|s)\b",
    re.IGNORECASE,
)


def parse_duration_seconds(text: str) -> Optional[int]:
    """'1 h 30 m', '25 minutes', 'ninety seconds', '5m' -> seconds."""
    total = 0
    found = False
    for match in _DURATION_RE.finditer(text):
        value = _to_int(match.group("value"))
        if value is None:
            continue
        unit = match.group("unit").lower()
        if unit.startswith(("hour", "hr", "h")):
            total += value * 3600
        elif unit.startswith(("min", "m")):
            total += value * 60
        else:
            total += value
        found = True
    if not found:
        # Bare number in a timer phrase means minutes.
        bare = re.search(r"\b(\d{1,3})\b", text)
        if bare:
            return int(bare.group(1)) * 60
        return None
    return total or None


_CLOCK_RE = re.compile(
    r"\b(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*(?P<ampm>am|pm|a\.m\.|p\.m\.|in the morning|in the evening|in the afternoon|at night|morning|evening|afternoon|night|o'clock)?\b",
    re.IGNORECASE,
)


def parse_clock_time(text: str) -> Optional[str]:
    """Extract a wall-clock time as 'HH:MM' (24h)."""
    low = text.lower()
    for match in _CLOCK_RE.finditer(low):
        hour = int(match.group("hour"))
        minute = int(match.group("minute") or 0)
        ampm = (match.group("ampm") or "").replace(".", "").strip().lower()
        if "pm" in ampm or "evening" in ampm or "night" in ampm or "afternoon" in ampm:
            if hour < 12:
                hour += 12
        elif "am" in ampm or "morning" in ampm:
            if hour == 12:
                hour = 0
        elif "o'clock" in ampm or re.search(rf"\b(at|for)\s+{hour}\b", low):
            if hour <= 5:
                hour += 12
        else:
            if match.group("minute") is None and not ampm:
                continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}"
    return None


_STOPWORDS_TASK = re.compile(
    r"^(please\s+)?(can you\s+)?(add|create|new|make)\s+(a\s+)?(task|todo|to-do)\s*(to|called|named|:)?\s*",
    re.IGNORECASE,
)

# "the last one", "it", "that", "the previous task" — a follow-up that points
# back at whatever the last command touched instead of naming it.
_REF_LAST = re.compile(r"\b(last|previous|latest|recent|that)\b", re.IGNORECASE)
_REF_PRONOUN = re.compile(r"\b(it|that|this|those|them)\b", re.IGNORECASE)


# The actions a reference can follow. A reference only counts when paired with
# one of these — "delete it", "mark that done" — never a bare pronoun, so
# "what time is it" is left alone.
_REF_ACTION = re.compile(
    r"\b(delete|remove|discard|clear|get rid of|cancel|complete|completed|done|finish"
    r"|finished|tick|check off|mark)\b",
    re.IGNORECASE,
)


def _reference_target(low: str) -> Optional[str]:
    """Return 'last' or 'it' when the sentence acts on a prior item by position
    or pronoun rather than by name, else None.

    Requires both an action word (delete/complete/...) and a reference word, so
    an incidental pronoun like "what time is it" is never treated as one. The
    executor resolves 'last'/'it' against the conversation memory.
    """
    if not _REF_ACTION.search(low):
        return None
    if _REF_LAST.search(low):
        return "last"
    # A pronoun paired with an action ("delete it", "remove that"), as long as
    # the sentence does not name a different thing to act on.
    if _REF_PRONOUN.search(low) and not re.search(
        r"\b(timer|alarm|stopwatch|pomodoro|light|lamp|led|reminder|screen)\b", low
    ):
        return "it"
    return None
_REMIND_PREFIX = re.compile(
    r"^(please\s+)?(can you\s+)?(remind me|reminder|set a reminder|remind)\s*(to|that|about)?\s*",
    re.IGNORECASE,
)
# Words that mean the relay-switched LED light. Plurals allowed ("lights",
# "LEDs"). "lead" and "lid" are how Whisper wrote a spoken "LED" / "एलईडी" in
# testing; this device has no lid, and neither word means anything else next
# to "on"/"off" here. "switch" and "device" are kept from
# the original list ("switch on", "turn the device off").
_LIGHT_WORDS = (
    r"(relays?|lights?|lamps?|bulbs?|leds?|lead|lid|tube\s*lights?|torch|fans?|plugs?|"
    r"sockets?|switch|device|power)"
)
_RELAY_OFF = r"(off|disable|deactivate|kill|shut|out|dark)"
_RELAY_ON = r"(on|enable|activate|start|bright)"
_RELAY_TOGGLE = r"(toggle|flip)"


def _relay_intent(low: str) -> Optional[Intent]:
    """Light on/off/toggle, or None if the sentence is not about the light."""
    if not re.search(rf"\b{_LIGHT_WORDS}\b", low):
        return None
    # "remind me to turn off the light" is a reminder, not a command for now.
    if re.search(r"\b(remind(er)?|task|todo|to-do)\b", low):
        return None
    if re.search(rf"\b{_RELAY_TOGGLE}\b", low):
        return Intent("relay.toggle", reply="Light toggled.")
    # Off is checked first: "turn off the light" contains no "on", but "switch
    # on ... no, off" should end off, and "off" is the more costly miss.
    if re.search(rf"\b{_RELAY_OFF}\b", low):
        return Intent("relay.off", {"on": False}, reply="Light turned off.")
    if re.search(rf"\b{_RELAY_ON}\b", low):
        return Intent("relay.on", {"on": True}, reply="Light turned on.")
    return None


# --------------------------------------------------------------------------- #
# Hindi / Hinglish
#
# Commands like "light chalu karo" or "5 minute ka timer lagao" are rewritten
# into the English phrasing the rules below already understand ("light on",
# "5 minutes timer set"). One set of rules then serves both languages, so a
# Hindi command and its English twin can never drift apart.
#
# Whisper may return Hindi in Roman script (Hinglish) or in Devanagari, so
# Devanagari is first transliterated into the same Roman words.
# --------------------------------------------------------------------------- #

# Plain substring replacement, longest first. \b is unusable here: Devanagari
# vowel signs are not word characters to `re`, so word boundaries fall inside
# words. Number words become Roman words, not digits, so "लगा दो" ("do it") is
# not mistaken for the number two; digits are only produced next to a unit.
_DEVANAGARI = [
    ("दोपहर", " dopahar "), ("सुबह", " subah "), ("सुभ", " subah "), ("शाम", " shaam "),
    ("रात", " raat "),
    ("कितने", " kitne "), ("बजे", " baje "), ("समय", " samay "), ("टाइमर", " timer "),
    # Spellings Whisper produced in testing: ताइमर, चालो, बुजा, मिनिट, and साथ
    # ("with") for सात (seven) — only ever meant as the number in a command.
    ("ताइमर", " timer "), ("टाईमर", " timer "), ("लाईट", " light "),
    ("साथ", " saat "), ("चालो", " chalu "), ("बुजाओ", " bujhao "), ("बुजा", " bujha "),
    ("मिनिट", " minute "), ("स्टॉपवॉच", " stopwatch "), ("स्टॉप", " stop "),
    ("वॉच", " watch "), ("वाच", " watch "), ("वॉट", " watch "), ("वाट", " watch "),
    ("टाइम", " time "), ("तारीख", " tarikh "), ("लाइट", " light "), ("बत्ती", " batti "),
    # Whisper also wrote एलेडी for a spoken "LED" in testing.
    ("एलईडी", " led "), ("एलेडी", " led "), ("एलइडी", " led "), ("एल ई डी", " led "),
    ("एल.ई.डी", " led "),
    ("बल्ब", " bulb "), ("पंखा", " pankha "), ("पंखे", " pankha "), ("अलार्म", " alarm "),
    ("स्टॉपवॉच", " stopwatch "), ("पोमोडोरो", " pomodoro "), ("मौसम", " mausam "),
    ("बारिश", " barish "), ("चालू", " chalu "), ("बंद", " band "), ("ऑन", " on "),
    ("ऑफ", " off "), ("जलाओ", " jalao "), ("जला", " jala "), ("बुझाओ", " bujhao "),
    ("बुझा", " bujha "), ("रोको", " roko "), ("रोक", " rok "), ("हटाओ", " hatao "),
    ("हटा", " hata "), ("शुरू", " shuru "), ("लगाओ", " lagao "), ("लगा", " laga "),
    ("वापस", " wapas "), ("मिनट", " minute "), ("सेकंड", " second "), ("सेकेंड", " second "),
    ("घंटे", " ghante "), ("घंटा", " ghanta "), ("साढ़े", " saade "), ("आधा", " aadha "),
    ("डेढ़", " dedh "), ("पैंतालीस", " paintalis "), ("पच्चीस", " pachees "),
    ("पंद्रह", " pandrah "), ("पन्द्रह", " pandrah "), ("चालीस", " chalis "),
    ("पचास", " pachas "), ("साठ", " saath "), ("बीस", " bees "), ("तीस", " tees "),
    ("बारह", " barah "), ("ग्यारह", " gyarah "), ("दस", " das "), ("नौ", " nau "),
    ("आठ", " aath "), ("सात", " saat "), ("छह", " chhah "), ("छः", " chhah "),
    ("पांच", " paanch "), ("पाँच", " paanch "), ("चार", " chaar "), ("तीन", " teen "),
    ("दो", " do "), ("एक", " ek "),
]
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_HINDI_NUMBERS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5,
    "chhe": 6, "chhah": 6, "che": 6, "saat": 7, "aath": 8, "nau": 9, "das": 10,
    "gyarah": 11, "barah": 12, "pandrah": 15, "pandra": 15, "bees": 20, "bis": 20,
    "pachees": 25, "pachchis": 25, "pachis": 25, "tees": 30, "tis": 30,
    "chalis": 40, "chaalis": 40, "paintalis": 45, "paintalees": 45,
    "pachas": 50, "pachaas": 50, "saath": 60,
}
_HINDI_UNIT = r"(?:minute|minutes|minat|mint|min|second|seconds|sekand|sec|ghante|ghanta|ghanton|hours?)"


def _hindi_clock(match: re.Match[str]) -> str:
    """'subah 7 baje' -> '7:00 am'. No qualifier -> "7 o'clock" (afternoon guess for 1-5)."""
    part = (match.group("part") or "").lower()
    hour = int(match.group("hour"))
    minute = match.group("minute") or "00"
    if part == "subah":
        return f" {hour}:{minute} am "
    if part in {"dopahar", "shaam", "sham"}:
        return f" {hour}:{minute} pm "
    if part == "raat":
        return f" {hour}:{minute} {'am' if hour == 12 or hour <= 4 else 'pm'} "
    return f" {hour}:{minute} " if match.group("minute") else f" {hour} o'clock "


def normalize_hindi(text: str) -> str:
    """Rewrite Hindi/Hinglish command words into English the rules understand.

    English input passes through essentially untouched: every rule targets a
    Hindi word, and number words only convert when followed by a time unit.
    """
    low = text.lower().translate(_DEVANAGARI_DIGITS)
    for hindi, roman in _DEVANAGARI:
        low = low.replace(hindi, roman)

    sub = re.sub
    # Question forms first — they reuse words ("baje", "time") the commands use.
    low = sub(r"\b(kitne\s+baje|kya\s+time|time\s+kya|samay\s+kya|time\s+batao|samay\s+batao)\b",
              " what time is it ", low)
    low = sub(r"\b(aaj\s+)?(kya|kaun\s*sa|konsa)?\s*(tarikh|tareekh|din)\s+(kya\s+)?(hai|batao)\b",
              " what is the date ", low)
    low = sub(r"\b(mausam|mosam)\b", " weather ", low)
    low = sub(r"\b(baarish|barish)\b", " raining ", low)

    # Durations: "aadha ghanta", "dedh ghanta", then "<number word> <unit>".
    low = sub(r"\b(aadha|adha)\s+(ghanta|ghante)\b", " 30 minutes ", low)
    low = sub(r"\bdedh\s+(ghanta|ghante)\b", " 90 minutes ", low)
    number_words = "|".join(sorted(_HINDI_NUMBERS, key=len, reverse=True))
    low = sub(rf"\b({number_words})\s+(?=(?:{_HINDI_UNIT}|baje)\b)",
              lambda m: f"{_HINDI_NUMBERS[m.group(1)]} ", low)
    low = sub(r"\b(minat|mint)\b", "minutes", low)
    low = sub(r"\bsekand\b", "seconds", low)
    low = sub(r"\b(ghante|ghanta|ghanton)\b", "hours", low)

    # Clock times: "saade 7" = 7:30, then "[subah|shaam|...] 7[:30] baje".
    low = sub(r"\bsaade\s+(\d{1,2})\b", r"\1:30", low)
    low = sub(r"\b(subha|subhah)\b", "subah", low)
    low = sub(r"\b(?P<part>subah|dopahar|shaam|sham|raat)?\s*(?P<hour>\d{1,2})(?::(?P<minute>\d{2}))?\s*baje\b",
              _hindi_clock, low)

    # Devices. Whisper writes a spoken "LED" as "LED", "L.E.D." or "L-E-D".
    low = sub(r"\bl\s*[.\-]?\s*e\s*[.\-]?\s*d\s*\.?(?=\s|$|s\b)", "led", low)
    low = sub(r"\bstop\s*(watch|wat|wach)\b", "stopwatch", low)
    low = sub(r"\b(batti|bati)\b", "light", low)
    low = sub(r"\b(pankha|pankhe)\b", "fan", low)

    # Verbs. Order matters: "wapas chalu" is resume, plain "chalu" is on.
    low = sub(r"\b(wapas|phir\s+se|fir\s+se)\s+(chalu|chaalu|shuru)\b", " resume ", low)
    low = sub(r"\b(chalu|chaalu|chalao|jala|jalao|on\s+kar\w*)\b", " on ", low)
    # "bant"/"bund": spellings Whisper produced for "band" in testing.
    low = sub(r"\b(band|bandh|bant|bund|bujha|bujhao|bujhado|off\s+kar\w*)\b", " off ", low)
    low = sub(r"\b(roko|rok\s+do|rok|ruko)\b", " pause ", low)
    low = sub(r"\b(hatao|hata\s+do|hata|mitao|cancel\s+kar\w*)\b", " cancel ", low)
    low = sub(r"\b(shuru|start\s+kar\w*)\b", " start ", low)
    low = sub(r"\b(lagao|laga\s+do|laga|lagaa|set\s+kar\w*)\b", " set ", low)
    return re.sub(r"\s+", " ", low).strip()


def parse(transcript: str) -> Intent:
    text = transcript.strip()
    low = normalize_hindi(text)

    if not low:
        return Intent("chat", confidence=0.0)

    # --- relay (the LED light) ---------------------------------------------- #
    # Any word for the light + any on/off word, in any order: "turn on the LED",
    # "lights off", "switch the LED on", "shut off the light", "LED band karo".
    # The earlier version only matched exact singular nouns next to "turn on" /
    # "switch on", so "LED", "lights" and "shut off" all fell through to chat.
    relay_intent = _relay_intent(low)
    if relay_intent is not None:
        return relay_intent

    # --- stopwatch (check before timer: both mention start/stop) ------------ #
    if "stopwatch" in low:
        if re.search(r"\b(lap|split)\b", low):
            return Intent("stopwatch.lap", reply="Lap recorded.")
        if re.search(r"\b(reset|clear)\b", low):
            return Intent("stopwatch.reset", reply="Stopwatch reset.")
        if re.search(r"\b(stop|pause|halt|off)\b", low):
            return Intent("stopwatch.stop", reply="Stopwatch stopped.")
        return Intent("stopwatch.start", reply="Stopwatch running.")

    # --- pomodoro ----------------------------------------------------------- #
    if "pomodoro" in low or "focus session" in low or "deep work" in low:
        if re.search(r"\b(stop|end|cancel|quit|off)\b", low):
            return Intent("pomodoro.stop", reply="Pomodoro has been stopped.")
        if re.search(r"\b(pause|hold)\b", low):
            return Intent("pomodoro.pause", reply="Pomodoro paused.")
        if re.search(r"\b(resume|continue)\b", low):
            return Intent("pomodoro.resume", reply="Pomodoro resumed.")
        if re.search(r"\b(skip|next)\b", low):
            return Intent("pomodoro.skip", reply="Skipping ahead.")
        entities: dict[str, Any] = {}
        duration = parse_duration_seconds(low) if re.search(r"\d", low) else None
        if duration and duration >= 60:
            entities["focus_minutes"] = min(duration // 60, 180)
        mins = entities.get("focus_minutes", 25)
        return Intent("pomodoro.start", entities, reply=f"Pomodoro focus session started for {mins} minutes.")

    # --- alarm -------------------------------------------------------------- #
    if "alarm" in low or "wake me up" in low or "wake me" in low:
        if re.search(r"\b(cancell?|delete|remove|turn off|off|disable|stop|dismiss)\b", low):
            return Intent("alarm.cancel", reply="Alarm has been cancelled.")
        clock = parse_clock_time(low)
        if clock:
            try:
                h, m = map(int, clock.split(":"))
                period = "AM" if h < 12 else "PM"
                h12 = h % 12 or 12
                spoken_clock = f"{h12}:{m:02d} {period}"
            except Exception:
                spoken_clock = clock
            return Intent("alarm.set", {"time_of_day": clock}, reply=f"Alarm has been set for {spoken_clock}.")
        # A relative "wake me in 20 minutes" is a reminder, not an alarm (alarms
        # are a clock time). Fall through to the LLM, which maps it to
        # reminder.create — do not short-circuit to listing alarms. Only an
        # explicit "alarm" with no time lists them.
        if re.search(r"\bin\s+.*\b(minute|min|hour|second|sec)", low):
            return Intent("chat", confidence=0.0)
        if "alarm" in low:
            return Intent("alarm.list", reply="Here are your alarms.")
        return Intent("chat", confidence=0.0)

    # --- reminder ----------------------------------------------------------- #
    if re.search(r"\bremind(er)?\b", low):
        body = _REMIND_PREFIX.sub("", text).strip()
        in_minutes: Optional[int] = None
        at_time = parse_clock_time(low)
        in_match = re.search(r"\bin\s+(.+)$", body, re.IGNORECASE)
        if in_match:
            seconds = parse_duration_seconds(in_match.group(1))
            if seconds:
                in_minutes = max(seconds // 60, 1)
                body = body[: in_match.start()].strip()
        body = re.sub(r"\bat\s+\d{1,2}(:\d{2})?\s*(am|pm)?\s*$", "", body, flags=re.IGNORECASE).strip()
        body = body.rstrip(" .,")
        if not body:
            body = "Reminder"
        payload: dict[str, Any] = {"text": body}
        if in_minutes:
            payload["in_minutes"] = in_minutes
        elif at_time:
            payload["at_time"] = at_time
        else:
            payload["in_minutes"] = 10
        return Intent("reminder.create", payload, reply=f"Reminder saved: {body}.")

    # --- tasks -------------------------------------------------------------- #
    # A follow-up like "delete the last task", "remove it", "mark that done".
    # Only treated as a task reference when it has no title of its own — it
    # leans entirely on what the previous turn created (resolved in the
    # executor against conversation memory).
    task_ref = _reference_target(low)
    if re.search(r"\b(task|todo|to-do)\b", low) or task_ref:
        remove = re.search(r"\b(delete|remove|discard|cancel|clear|get rid of)\b", low)
        complete = re.search(r"\b(complete|completed|done|finish|finished|tick|check off)\b", low)

        if remove or complete:
            name = "task.delete" if remove else "task.complete"
            default_reply = "Removed." if remove else "Marked done."
            if task_ref:
                # "the last task" / "it" / "that one" — no title, resolve by ref.
                return Intent(name, {"ref": task_ref}, reply=default_reply)
            # A title was named: "delete the groceries task".
            title = re.sub(
                r"\b(mark|complete|completed|done|finish|finished|delete|remove|discard|cancel|clear"
                r"|get rid of|as|the|task|todo|to-do)\b",
                " ",
                text,
                flags=re.IGNORECASE,
            )
            return Intent(name, {"title": re.sub(r"\s+", " ", title).strip(" .,")}, reply=default_reply)

        if re.search(r"\b(list|show|what are|read)\b", low):
            return Intent("task.list", reply="Here is your task list.")
        title = _STOPWORDS_TASK.sub("", text).strip(" .,")
        priority = "normal"
        if re.search(r"\b(urgent|important|high priority|asap)\b", low):
            priority = "high"
            title = re.sub(r"\b(urgent|important|high priority|asap)\b", "", title, flags=re.IGNORECASE)
        title = re.sub(r"\s+", " ", title).strip(" .,")
        if title:
            return Intent(
                "task.create",
                {"title": title, "priority": priority},
                reply=f"Added task: {title}.",
            )

    # --- timer -------------------------------------------------------------- #
    if re.search(r"\btimer\b", low) or re.search(r"\b(set|start)\b.*\bfor\b.*\b(minute|min|hour|second|sec)\b", low):
        if re.search(r"\b(cancell?|stop|clear|delete|kill|off)\b", low):
            return Intent("timer.cancel", reply="Timer has been cancelled.")
        if re.search(r"\b(pause|hold)\b", low):
            return Intent("timer.pause", reply="Timer paused.")
        if re.search(r"\b(resume|continue|unpause)\b", low):
            return Intent("timer.resume", reply="Timer resumed.")
        if re.search(r"\b(how (much|long)|remaining|left|status)\b", low):
            return Intent("timer.status")
        seconds = parse_duration_seconds(low)
        if seconds:
            label_match = re.search(r"\bfor\s+(?:my\s+)?([a-z ]{3,30})\s+timer\b", low)
            entities = {"duration_seconds": seconds}
            if label_match:
                entities["label"] = label_match.group(1).strip().title()
            return Intent("timer.start", entities, reply=f"Timer has been set for {_spoken_duration(seconds)}.")
        # "timer chalu karo" / "start the timer" with no duration: start the same
        # 10-minute default the device's own double tap uses, rather than asking.
        # Only when no number was spoken at all — if one was and still did not
        # parse, guessing 10 minutes would be wrong; the executor asks instead.
        spoke_number = re.search(r"\d", low) or re.search(
            r"\b(" + "|".join(_HINDI_NUMBERS) + r")\b", low)
        if spoke_number and re.search(r"\b(on|start|set)\b", low):
            return Intent("timer.start", {})
        if re.search(r"\b(on|start|set)\b", low):
            seconds = 10 * 60
            return Intent("timer.start", {"duration_seconds": seconds},
                          reply=f"Timer has been set for {_spoken_duration(seconds)}.")
        return Intent("timer.status")

    # --- study notes / quiz ------------------------------------------------- #
    if (
        re.search(
            r"\b(ask|give)(?:\s+me)?(?:\s+a|\s+another)?\s+questions?\s+(?:from|about|on)\s+(?:my\s+|the\s+)?(?:notes|pdf|document|study notes)\b",
            low,
        )
        or re.search(r"\bquiz\s+me\b|\btest\s+me\b", low)
        or re.search(r"\b(ask|give)(?:\s+me)?\s+(?:a\s+|another\s+)?question\s+from\s+(?:my\s+|the\s+)?(?:notes|pdf|document)\b", low)
        or re.search(r"\b(next|another)\s+question\b", low)
        or re.search(r"\bnotes?\s+se\s+(?:question|sawal|prashna)\b", low)
        or re.search(r"\bnotes?\s+(?:ka|se)\s+quiz\b", low)
        or re.search(r"\b(study|revision)\s+quiz\b", low)
    ):
        topic = ""
        m = re.search(r"\b(?:on|about|from)\s+([a-zA-Z0-9_\- ]+?)(?:\s+notes|\s+pdf)?$", low)
        if m:
            candidate = m.group(1).strip()
            if candidate not in {"my", "the", "my notes", "the notes", "notes", "pdf", "study notes"}:
                topic = candidate
        return Intent("notes.quiz", {"topic": topic} if topic else {})

    # --- weather ------------------------------------------------------------ #
    # Checked before the clock rules: "what's the weather like today" contains
    # "today", and several time phrasings would otherwise win the race.
    if re.search(r"\b(weather|forecast|temperature|how (hot|cold)|raining|rain today)\b", low):
        return Intent("weather.current")

    # --- clock -------------------------------------------------------------- #
    if re.search(r"\bwhat(?:'s| is)? the time\b|\bwhat time is it\b|\bcurrent time\b", low):
        return Intent("clock.time")
    if re.search(r"\bwhat(?:'s| is)? (?:the )?date\b|\bwhat day is it\b", low):
        return Intent("clock.date")

    # --- device ------------------------------------------------------------- #
    if re.search(r"\b(battery|charge level)\b", low):
        return Intent("device.battery")
    if re.search(r"\b(status|how are you doing|diagnostics)\b", low) and "device" in low:
        return Intent("device.status")

    return Intent("chat", confidence=0.0)


def _spoken_duration(seconds: int) -> str:
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    parts: list[str] = []
    if hours:
        parts.append(f"{hours} hour" + ("s" if hours != 1 else ""))
    if minutes:
        parts.append(f"{minutes} minute" + ("s" if minutes != 1 else ""))
    if secs and not hours:
        parts.append(f"{secs} second" + ("s" if secs != 1 else ""))
    return " ".join(parts) or f"{seconds} second"
