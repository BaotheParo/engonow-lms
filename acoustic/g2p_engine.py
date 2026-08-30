"""
acoustic/g2p_engine.py
======================
Grapheme-to-Phoneme (G2P) and CMUdict Lexicon Engine for IELTS Speaking.
Maps English text into IPA phonetic representations, derives syllable counts,
and extracts canonical lexical stress patterns.
"""

from typing import List, Dict, Tuple, Optional
import re
import logging

logger = logging.getLogger("G2PEngine")


class G2PEngine:
    """
    Phonetic dictionary and G2P converter providing ARPAbet/IPA transcription
    and syllable stress patterns.
    """

    # --------------------------------------------------------------------------
    # ARPAbet (39 Phonemes) to International Phonetic Alphabet (IPA) Mapping
    # --------------------------------------------------------------------------
    ARPABET_TO_IPA: Dict[str, str] = {
        # Vowels & Diphthongs
        "AA": "ɑ",
        "AE": "æ",
        "AH": "ʌ",
        "AO": "ɔ",
        "AW": "aʊ",
        "AY": "aɪ",
        "EH": "ɛ",
        "ER": "ɜː",
        "EY": "eɪ",
        "IH": "ɪ",
        "IY": "iː",
        "OW": "oʊ",
        "OY": "ɔɪ",
        "UH": "ʊ",
        "UW": "uː",
        # Consonants
        "B": "b",
        "CH": "tʃ",
        "D": "d",
        "DH": "ð",
        "F": "f",
        "G": "ɡ",
        "HH": "h",
        "JH": "dʒ",
        "K": "k",
        "L": "l",
        "M": "m",
        "N": "n",
        "NG": "ŋ",
        "P": "p",
        "R": "r",
        "S": "s",
        "SH": "ʃ",
        "T": "t",
        "TH": "θ",
        "V": "v",
        "W": "w",
        "Y": "j",
        "Z": "z",
        "ZH": "ʒ",
    }

    VOWEL_ARPABET_PREFIXES = {
        "AA", "AE", "AH", "AO", "AW", "AY", "EH", "ER", "EY", "IH", "IY", "OW", "OY", "UH", "UW"
    }

    # --------------------------------------------------------------------------
    # Canonical CMUdict Core Lexicon with Stress Annotations (0=unstr, 1=pri, 2=sec)
    # --------------------------------------------------------------------------
    CMUDICT_LEXICON: Dict[str, List[str]] = {
        "development": ["D", "IH0", "V", "EH1", "L", "AH0", "P", "M", "AH0", "N", "T"],
        "technology": ["T", "EH0", "K", "N", "AA1", "L", "AH0", "JH", "IY0"],
        "photograph": ["F", "OW1", "T", "AH0", "G", "R", "AE2", "F"],
        "education": ["EH2", "JH", "AH0", "K", "EY1", "SH", "AH0", "N"],
        "think": ["TH", "IH1", "NG", "K"],
        "thinking": ["TH", "IH1", "NG", "K", "IH0", "NG"],
        "thought": ["TH", "AO1", "T"],
        "the": ["DH", "AH0"],
        "this": ["DH", "IH1", "S"],
        "that": ["DH", "AE1", "T"],
        "there": ["DH", "EH1", "R"],
        "they": ["DH", "EY1"],
        "speaking": ["S", "P", "IY1", "K", "IH0", "NG"],
        "pronunciation": ["P", "R", "OW0", "N", "AH2", "N", "S", "IY0", "EY1", "SH", "AH0", "N"],
        "fluency": ["F", "L", "UW1", "AH0", "N", "S", "IY0"],
        "accuracy": ["AE1", "K", "Y", "ER0", "AH0", "S", "IY0"],
        "important": ["IH0", "M", "P", "AO1", "R", "T", "AH0", "N", "T"],
        "economic": ["EH2", "K", "AH0", "N", "AA1", "M", "IH0", "K"],
        "university": ["Y", "UW2", "N", "AH0", "V", "ER1", "S", "AH0", "T", "IY0"],
        "environment": ["IH0", "N", "V", "AY1", "R", "AH0", "N", "M", "AH0", "N", "T"],
        "government": ["G", "AH1", "V", "ER0", "N", "M", "AH0", "N", "T"],
        "international": ["IH2", "N", "T", "ER0", "N", "AE1", "SH", "AH0", "N", "AH0", "L"],
        "community": ["K", "AH0", "M", "Y", "UW1", "N", "AH0", "T", "IY0"],
        "transportation": ["T", "R", "AE2", "N", "S", "P", "ER0", "T", "EY1", "SH", "AH0", "N"],
        "student": ["S", "T", "UW1", "D", "AH0", "N", "T"],
        "students": ["S", "T", "UW1", "D", "AH0", "N", "T", "S"],
        "computer": ["K", "AH0", "M", "P", "Y", "UW1", "T", "ER0"],
        "information": ["IH2", "N", "F", "ER0", "M", "EY1", "SH", "AH0", "N"],
        "society": ["S", "AH0", "S", "AY1", "AH0", "T", "IY0"],
        "different": ["D", "IH1", "F", "ER0", "AH0", "N", "T"],
        "sentence": ["S", "EH1", "N", "T", "AH0", "N", "S"],
        "middle": ["M", "IH1", "D", "AH0", "L"],
        "ending": ["EH1", "N", "D", "IH0", "NG"],
        "hello": ["HH", "AH0", "L", "OW1"],
        "world": ["W", "ER1", "L", "D"],
        "good": ["G", "UH1", "D"],
        "well": ["W", "EH1", "L"],
        "like": ["L", "AY1", "K"],
        "you": ["Y", "UW1"],
        "know": ["N", "OW1"],
    }

    def __init__(self, custom_lexicon: Optional[Dict[str, List[str]]] = None):
        self.lexicon = dict(self.CMUDICT_LEXICON)
        if custom_lexicon:
            self.lexicon.update(custom_lexicon)

    def word_to_phonemes(self, word: str) -> List[str]:
        """
        Converts an English word to a sequence of IPA phonemes.

        Parameters:
            word: Target orthographic word.

        Returns:
            List of IPA phoneme strings (e.g., 'think' -> ['θ', 'ɪ', 'ŋ', 'k']).
        """
        # Strip all punctuation and special characters (e.g., 'technology,' -> 'technology')
        clean_word = re.sub(r"[^a-zA-Z]", "", word).lower()
        if not clean_word:
            return []

        if clean_word in self.lexicon:
            arpa_list = self.lexicon[clean_word]
            return [self._arpa_to_ipa(phone) for phone in arpa_list]

        # Rule-based fallback for OOV words
        return self._rule_based_g2p(clean_word)

    def word_stress_pattern(self, word: str) -> Tuple[int, List[int]]:
        """
        Extracts syllable count and the canonical stress pattern for a word.

        Parameters:
            word: Target word.

        Returns:
            (syllable_count, [stress_per_syllable])
            e.g., 'development' -> (4, [0, 1, 0, 0])
        """
        # Strip all punctuation and special characters
        clean_word = re.sub(r"[^a-zA-Z]", "", word).lower()
        if not clean_word:
            return (0, [])

        if clean_word in self.lexicon:
            arpa_list = self.lexicon[clean_word]
            stress_list = []
            for phone in arpa_list:
                # Vowel phones in CMUdict end with '0', '1', or '2'
                if len(phone) >= 3 and phone[-1] in ("0", "1", "2"):
                    stress_list.append(int(phone[-1]))
                elif any(phone.startswith(v) for v in self.VOWEL_ARPABET_PREFIXES) and phone[-1].isdigit():
                    stress_list.append(int(phone[-1]))

            if stress_list:
                return (len(stress_list), stress_list)

        # Rule-based fallback for OOV polysyllabic estimation
        return self._estimate_oov_stress(clean_word)

    def _arpa_to_ipa(self, arpa_phone: str) -> str:
        """Strips digit stress markers and converts ARPAbet to IPA."""
        base = re.sub(r"\d", "", arpa_phone).upper()
        return self.ARPABET_TO_IPA.get(base, base.lower())

    def _rule_based_g2p(self, word: str) -> List[str]:
        """Simple rule-based G2P phonetic mapping for OOV words."""
        ipa_list = []
        i = 0
        w_len = len(word)
        while i < w_len:
            # 2-char graphemes
            if i + 1 < w_len:
                digraph = word[i : i + 2]
                if digraph == "th":
                    ipa_list.append("θ")
                    i += 2
                    continue
                elif digraph == "sh":
                    ipa_list.append("ʃ")
                    i += 2
                    continue
                elif digraph == "ch":
                    ipa_list.append("tʃ")
                    i += 2
                    continue
                elif digraph == "ph":
                    ipa_list.append("f")
                    i += 2
                    continue
                elif digraph == "ng":
                    ipa_list.append("ŋ")
                    i += 2
                    continue
                elif digraph == "ee":
                    ipa_list.append("iː")
                    i += 2
                    continue
                elif digraph == "oo":
                    ipa_list.append("uː")
                    i += 2
                    continue

            # 1-char grapheme
            c = word[i]
            single_map = {
                "a": "æ", "b": "b", "c": "k", "d": "d", "e": "ɛ",
                "f": "f", "g": "ɡ", "h": "h", "i": "ɪ", "j": "dʒ",
                "k": "k", "l": "l", "m": "m", "n": "n", "o": "ɒ",
                "p": "p", "q": "k", "r": "r", "s": "s", "t": "t",
                "u": "ʌ", "v": "v", "w": "w", "x": "ks", "y": "j",
                "z": "z"
            }
            ipa_list.append(single_map.get(c, c))
            i += 1
        return ipa_list

    def _estimate_oov_stress(self, word: str) -> Tuple[int, List[int]]:
        """Estimates syllable count and stress pattern for OOV words using heuristic suffix rules."""
        # Simple vowel counting for syllable count
        vowels = "aeiouy"
        w = word.lower()
        count = 0
        prev_is_vowel = False
        for c in w:
            is_vowel = c in vowels
            if is_vowel and not prev_is_vowel:
                count += 1
            prev_is_vowel = is_vowel

        # Adjust silent 'e' at end
        if w.endswith("e") and count > 1 and not w.endswith("le"):
            count -= 1
        count = max(1, count)

        if count == 1:
            return (1, [1])

        # Stress heuristics
        stresses = [0] * count
        if w.endswith(("tion", "sion", "ic", "ical", "ity", "ious")):
            # Penultimate stress
            pri_idx = max(0, count - 2)
        elif count == 2:
            pri_idx = 0  # Default initial stress for 2-syllable words
        elif count >= 3:
            pri_idx = 1  # Default antepenultimate / 2nd syllable
        else:
            pri_idx = 0

        stresses[pri_idx] = 1
        return (count, stresses)
