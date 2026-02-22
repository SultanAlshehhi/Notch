"""
matching_engine.py — Word-matching logic for script alignment.

Takes the full script and recognised words from the speech engine, and
figures out where in the script the speaker currently is. Uses a look-ahead
window and fuzzy matching to tolerate stumbles, skips, and mispronunciations.
"""

import re
from typing import Optional, List

from thefuzz import fuzz


class MatchingEngine:
    """Tracks the user's reading position inside the loaded script."""

    # Minimum fraction of script word length required for a partial single-word match (stricter = fewer false advances)
    MIN_PARTIAL_RATIO = 0.65
    MIN_PARTIAL_CHARS = 3

    def __init__(self, look_ahead: int = 30, match_threshold: int = 55):
        self.look_ahead = look_ahead
        self.match_threshold = match_threshold

        self._words: List[str] = []
        self._raw_words: List[str] = []
        self._position: int = 0
        self._word_char_offsets: List[int] = []
        self._raw_text: str = ""
        self._last_spoken_len: int = 0  # track partial growth

    # ── Public API ───────────────────────────────────────────────────

    def load_script(self, text: str):
        """Parse the script into a word list and build offset map."""
        self._raw_text = text
        self._words = []
        self._raw_words = []
        self._word_char_offsets = []
        self._position = 0
        self._last_spoken_len = 0

        for m in re.finditer(r"\S+", text):
            raw = m.group()
            self._raw_words.append(raw)
            self._words.append(self._normalise(raw))
            self._word_char_offsets.append(m.start())

    @property
    def word_count(self) -> int:
        return len(self._words)

    @property
    def position(self) -> int:
        return self._position

    @property
    def progress(self) -> float:
        if not self._words:
            return 0.0
        return self._position / len(self._words)

    def char_offset_at(self, word_index: int) -> int:
        """Return the character offset in the raw text for a given word index."""
        if not self._word_char_offsets:
            return 0
        idx = max(0, min(word_index, len(self._word_char_offsets) - 1))
        return self._word_char_offsets[idx]

    def word_span(self, word_index: int) -> tuple[int, int]:
        """Return (start, end) char offsets for a word, inclusive of trailing space."""
        if not self._word_char_offsets:
            return (0, 0)
        idx = max(0, min(word_index, len(self._word_char_offsets) - 1))
        start = self._word_char_offsets[idx]
        if idx + 1 < len(self._word_char_offsets):
            end = self._word_char_offsets[idx + 1]
        else:
            end = len(self._raw_text)
        return (start, end)

    def reset(self):
        self._position = 0
        self._last_spoken_len = 0

    def set_position(self, word_index: int) -> None:
        """Set reading position (e.g. when user scrolls to skip back/forward)."""
        if not self._words:
            return
        self._position = max(0, min(word_index, len(self._words) - 1))

    def match_spoken(
        self,
        spoken_text: str,
        allow_extended: bool = True,
        max_advance: Optional[int] = None,
    ) -> Optional[int]:
        """
        Given a string of spoken words from the recogniser, find the best
        matching position in the script and advance the internal pointer.

        Returns the new word-index position, or None if no match was found.
        """
        if not self._words:
            return None

        spoken_words = [self._normalise(w) for w in spoken_text.split() if w.strip()]
        if not spoken_words:
            return None

        # Determine how many new words arrived since last call
        new_word_count = len(spoken_words)

        # Use a sliding tail window: try multiple tail sizes for robustness
        # This handles both single-word and multi-word matching
        best_score = 0
        best_index = None

        # Search windows: normal look-ahead, then extended for catch-up
        window_start = max(0, self._position - 2)  # small lookback for tolerance
        window_end = min(len(self._words), self._position + self.look_ahead)

        # If near the end, widen the window
        if window_end - window_start < 5 and len(self._words) > 5:
            window_start = max(0, len(self._words) - self.look_ahead)
            window_end = len(self._words)

        # Try different tail sizes: 1, 2, 3, and up to 5 words from the end
        tail_sizes = []
        for sz in [1, 2, 3, 4, 5]:
            if sz <= len(spoken_words):
                tail_sizes.append(sz)

        for tail_sz in tail_sizes:
            spoken_tail = spoken_words[-tail_sz:]
            spoken_phrase = " ".join(spoken_tail)

            for i in range(window_start, window_end):
                snippet = self._words[i : i + tail_sz]
                if len(snippet) != tail_sz:
                    continue
                script_phrase = " ".join(snippet)

                # Use token_sort_ratio for single words (handles slight variations)
                # and ratio for phrases
                if tail_sz == 1:
                    # Stricter partials: require enough of the word before advancing (avoids "any word" advancing)
                    spoken_len = len(spoken_phrase)
                    script_len = len(script_phrase)
                    if spoken_len < self.MIN_PARTIAL_CHARS:
                        continue
                    if script_len > 0 and spoken_len < script_len * self.MIN_PARTIAL_RATIO:
                        continue
                    score = fuzz.ratio(spoken_phrase, script_phrase)
                    # Boost exact single-word matches
                    if spoken_phrase == script_phrase:
                        score = 100
                else:
                    score = fuzz.ratio(spoken_phrase, script_phrase)

                # Prefer matches further along (closer to where we expect the reader)
                # Give a small bonus for being near the current position
                position_bonus = 0
                match_end = i + tail_sz - 1
                if match_end >= self._position:
                    position_bonus = 2  # slight forward preference

                adjusted = score + position_bonus

                if adjusted > best_score:
                    best_score = adjusted
                    best_index = i + tail_sz - 1

        # Accept match if above threshold
        threshold = self.match_threshold
        if best_score >= threshold and best_index is not None:
            if best_index >= self._position:
                if max_advance is None or (best_index - self._position) <= max_advance:
                    self._position = best_index
                else:
                    return None
            self._last_spoken_len = new_word_count
            return self._position

        # ── Extended catch-up scan (user skipped ahead) ──────────────
        if not allow_extended:
            self._last_spoken_len = new_word_count
            return None
        extended_end = min(len(self._words), self._position + self.look_ahead * 5)
        for tail_sz in [3, 4, 5]:
            if tail_sz > len(spoken_words):
                continue
            spoken_tail = spoken_words[-tail_sz:]
            spoken_phrase = " ".join(spoken_tail)

            for i in range(window_end, extended_end):
                snippet = self._words[i : i + tail_sz]
                if len(snippet) != tail_sz:
                    continue
                script_phrase = " ".join(snippet)
                score = fuzz.ratio(spoken_phrase, script_phrase)
                if score >= threshold + 10:  # stricter for big jumps
                    self._position = i + tail_sz - 1
                    self._last_spoken_len = new_word_count
                    return self._position

        self._last_spoken_len = new_word_count
        return None

    # ── Internals ────────────────────────────────────────────────────

    @staticmethod
    def _normalise(word: str) -> str:
        """Lower-case and strip punctuation for comparison."""
        return re.sub(r"[^\w']", "", word.lower())
