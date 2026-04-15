# dedup.py
"""内容去重：检测新生成的剧本与已有内容的相似度，避免同质化。

用法:
    from dedup import ContentDedup
    dedup = ContentDedup("outputs")
    is_dup, sim, match = dedup.check("新剧本文本...")
    if is_dup:
        print(f"与 {match} 相似度 {sim:.0%}，需换角度重写")
"""
import math
import os
import re
from collections import Counter


def _tokenize(text: str) -> list[str]:
    """简易中文分词：按标点和空白切分，过滤短 token。"""
    tokens = re.findall(r"[\u4e00-\u9fa5]{2,}|[a-zA-Z]+", text)
    return tokens


def _tf(tokens: list[str]) -> dict[str, float]:
    counts = Counter(tokens)
    total = len(tokens) or 1
    return {t: c / total for t, c in counts.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    dot = sum(a[k] * b[k] for k in keys)
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a < 1e-9 or norm_b < 1e-9:
        return 0.0
    return dot / (norm_a * norm_b)


class ContentDedup:
    """扫描 outputs/ 下所有 story_draft.txt，对新内容做相似度检测。"""

    def __init__(self, outputs_dir: str = "outputs", threshold: float = 0.6):
        self.outputs_dir = outputs_dir
        self.threshold = threshold
        self._corpus: dict[str, dict[str, float]] = {}
        self._load_corpus()

    def _load_corpus(self):
        if not os.path.isdir(self.outputs_dir):
            return
        for folder in os.listdir(self.outputs_dir):
            draft = os.path.join(self.outputs_dir, folder, "story_draft.txt")
            if os.path.isfile(draft):
                try:
                    with open(draft, "r", encoding="utf-8") as f:
                        text = f.read()
                    self._corpus[folder] = _tf(_tokenize(text))
                except Exception:
                    pass

    def check(self, new_text: str) -> tuple[bool, float, str]:
        """返回 (is_duplicate, max_similarity, most_similar_folder)。"""
        new_tf = _tf(_tokenize(new_text))
        max_sim = 0.0
        match = ""
        for folder, existing_tf in self._corpus.items():
            sim = _cosine(new_tf, existing_tf)
            if sim > max_sim:
                max_sim = sim
                match = folder
        return max_sim >= self.threshold, max_sim, match

    def add(self, folder_name: str, text: str):
        """将新内容加入语料库（生产完成后调用）。"""
        self._corpus[folder_name] = _tf(_tokenize(text))

    @property
    def corpus_size(self) -> int:
        return len(self._corpus)
