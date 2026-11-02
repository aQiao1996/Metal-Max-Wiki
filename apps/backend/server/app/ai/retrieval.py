import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
from math import log
from typing import Protocol
from unicodedata import normalize

from app.ai.evidence import EvidenceChunk, load_evidence_chunks

_STOP_PHRASES = (
    "请问",
    "请帮我",
    "帮我",
    "告诉我",
    "能不能",
    "可不可以",
    "有没有",
    "是什么",
    "为什么",
    "怎么样",
    "怎么",
    "如何",
    "可以",
    "哪个",
    "哪些",
    "什么",
    "一下",
    "是否",
    "多少",
    "哪里",
    "应该",
    "这个",
    "那个",
    "一个",
    "这些",
    "那些",
    "的",
    "了",
    "吗",
    "呢",
    "啊",
    "和",
    "与",
    "请",
    "重装机兵2r",
    "重装机兵",
    "mm2r",
    "0.99",
    "使用",
    "资料",
    "游戏",
)
_WEAK_TERMS = {
    "装备",
    "武器",
    "战车",
    "引擎",
    "职业",
    "技能",
    "道具",
    "任务",
    "攻略",
    "物品",
    "攻击",
    "击力",
    "防御",
    "御力",
    "命中",
    "回避",
    "重量",
    "价格",
    "范围",
    "效果",
    "作用",
    "获取",
    "获得",
    "特性",
    "数值",
    "条件",
    "说明",
    "最大",
    "最小",
    "上限",
    "下限",
    "普通",
    "改造",
    "星级",
    "载重",
    "比较",
    "区别",
    "版本",
    "汉化",
    "支持",
    "需要",
    "能否",
    "有效",
    "当前",
    "实际",
    "完成",
    "触发",
    "地点",
    "前提",
    "奖励",
    "内容",
    "步骤",
    "流程",
    "用途",
    "对象",
    "消耗",
    "限制",
    "学习",
    "来源",
    "原文",
    "参考",
    "实机",
    "核验",
    "确认",
    "记录",
    "掉落",
    "概率",
}
_FOCUS_PHRASES = ("双引擎", "双c装置", "副职业", "独立掉落", "随机遭遇", "超改造", "马力强化")
_SYNONYMS = {
    "战士": "士兵",
    "大砲": "主炮",
    "機銃": "副炮",
    "エンジン": "引擎",
    "cユニット": "c装置",
    "s-e": "特殊装备",
    "s－e": "特殊装备",
    "砲": "炮",
    "車": "车",
    "罰": "罚",
}


def _normalized(text: str) -> str:
    value = normalize("NFKC", text).casefold()
    for source, target in _SYNONYMS.items():
        value = value.replace(source, target)
    return value


def _terms(text: str) -> frozenset[str]:
    value = _normalized(text)
    for phrase in _STOP_PHRASES:
        value = value.replace(phrase, " ")
    terms = set(re.findall(r"[a-z][a-z0-9]*(?:[.-][a-z0-9]+)*|[0-9]+(?:\.[0-9]+)?", value))
    for segment in re.findall(r"[\u3040-\u30ff\u3400-\u9fff]+", value):
        terms.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return frozenset(term for term in terms if len(term) > 1 or term.isdecimal())


@dataclass(frozen=True)
class RetrievalResult:
    chunks: tuple[EvidenceChunk, ...]
    budget_limited: bool = False
    missing_conditions: tuple[str, ...] = ()


class EvidenceRetriever(Protocol):
    """词法检索与后续 pgvector 实现共享证据和预算契约。"""

    def retrieve(self, question: str, *, limit: int, max_context_chars: int) -> RetrievalResult:
        """返回预算内的完整证据，不截断段落、表格行或条件。"""
        ...


@dataclass(frozen=True)
class _IndexedChunk:
    chunk: EvidenceChunk
    terms: frozenset[str]
    title_terms: frozenset[str]
    names: tuple[str, ...]
    subjects: tuple[str, ...]
    body: str


@lru_cache(maxsize=1)
def _index() -> tuple[tuple[_IndexedChunk, ...], dict[str, float]]:
    indexed = tuple(
        _IndexedChunk(
            chunk=chunk,
            terms=_terms(f"{chunk.title}\n{chunk.text}"),
            title_terms=_terms(chunk.title),
            names=tuple(_normalized(name) for name in chunk.entity_names),
            subjects=tuple(_normalized(name) for name in chunk.subject_names),
            body=_normalized(chunk.text),
        )
        for chunk in load_evidence_chunks()
    )
    frequencies: Counter[str] = Counter(term for entry in indexed for term in entry.terms)
    weights = {
        term: log((len(indexed) + 1) / (count + 1)) + 1 for term, count in frequencies.items()
    }
    return indexed, weights


@dataclass(frozen=True)
class _Mention:
    entity_id: str
    name: str
    start: int
    end: int
    subject: bool


def _resolve_mentions(query: str, indexed: tuple[_IndexedChunk, ...]) -> tuple[_Mention, ...]:
    registry = {
        (entry.chunk.entity_id, entry.chunk.category, name, subject)
        for entry in indexed
        for subject, names in ((False, entry.names), (True, entry.subjects))
        for name in names
    }
    single_context = {
        "jobs": ("职业", "技能", "学习", "特技", "同伴", "成长"),
        "vehicles": ("战车", "底盘", "孔", "特性", "引擎", "获取", "获得", "改造", "配置"),
        "equipment": ("装备", "武器", "攻击", "防御", "引擎", "星", "获取"),
        "wanted-monsters": ("赏金", "怪物", "掉落", "击败", "位置"),
        "items": ("道具", "用途", "使用", "消耗", "获取", "获得", "任务"),
    }
    matches: list[_Mention] = []
    for entity_id, category, name, subject in registry:
        if not name:
            continue
        if (
            len(name) == 1
            and query.strip(" ？?。") != name
            and not any(word in query for word in single_context.get(category, ()))
        ):
            continue
        pattern = (
            rf"(?<![a-z0-9]){re.escape(name)}(?![a-z0-9])" if name.isascii() else re.escape(name)
        )
        matches.extend(
            _Mention(entity_id, name, m.start(), m.end(), subject)
            for m in re.finditer(pattern, query)
        )
    spans = sorted({(m.start, m.end) for m in matches}, key=lambda span: (span[0] - span[1], span))
    accepted: list[tuple[int, int]] = []
    for start, end in spans:
        if not any(start < other_end and end > other_start for other_start, other_end in accepted):
            accepted.append((start, end))
    return tuple(m for m in matches if (m.start, m.end) in accepted)


def _requested_stars(query: str) -> set[int]:
    stars = {int(number) for number in re.findall(r"([0-3])\s*星", query)}
    chinese_stars = {"零": 0, "一": 1, "二": 2, "三": 3}
    stars.update(chinese_stars[value] for value in re.findall(r"([零一二三])\s*星", query))
    if "无星" in query or "無星" in query:
        stars.add(0)
    stars.update(len(match) for match in re.findall(r"[★☆]{1,3}", query))
    return stars


def _bound_stars(query: str, mentions: tuple[_Mention, ...]) -> dict[str, set[int]]:
    bound: dict[str, set[int]] = defaultdict(set)
    for match in re.finditer(r"[0-3零一二三]\s*星|无星|無星|[★☆]{1,3}", query):
        distances = [
            (max(0, mention.start - match.end(), match.start() - mention.end), mention.entity_id)
            for mention in mentions
            if not mention.subject
        ]
        if not distances:
            continue
        nearest = min(distance for distance, _ in distances)
        if nearest > 16:
            continue
        for distance, entity_id in distances:
            if distance == nearest:
                bound[entity_id].update(_requested_stars(match.group()))
    entities = {mention.entity_id for mention in mentions if not mention.subject}
    requested = _requested_stars(query)
    last_end = max((mention.end for mention in mentions if not mention.subject), default=0)
    shared_suffix = len(entities) > 1 and re.match(r"的[0-3零一二三]\s*星", query[last_end:])
    if len(requested) == 1 and (
        shared_suffix or re.search(r"(?:都|均|同为).{0,3}[0-3零一二三]\s*星", query)
    ):
        return {entity_id: requested for entity_id in entities}
    return bound


def explicit_entity_stars(question: str) -> tuple[set[str], dict[str, set[int]]]:
    """独立解析问题里的完整实体名和显式星级，不从检索结果补齐输入。"""
    query = _normalized(question)
    indexed, _ = _index()
    mentions = _resolve_mentions(query, indexed)
    entities = {mention.entity_id for mention in mentions if not mention.subject}
    stars = _bound_stars(query, mentions)
    return entities, stars


class LexicalEvidenceRetriever:
    """以实体名、局部主题和有区分度的二元词检索，并为不同实体保留空间。"""

    def retrieve(self, question: str, *, limit: int, max_context_chars: int) -> RetrievalResult:
        query = _normalized(question)
        if re.search(r"(?:[4-9]|[1-9][0-9]+|[四五六七八九十])\s*星", query):
            return RetrievalResult(
                (), missing_conditions=("当前资料未收录所问的0至3星范围以外数值",)
            )
        terms = _terms(query)
        signals = terms - _WEAK_TERMS
        indexed, weights = _index()
        mentions = _resolve_mentions(query, indexed)
        mentioned = {mention.entity_id for mention in mentions if not mention.subject}
        subjects = {mention.entity_id for mention in mentions if mention.subject}
        local_names = {(mention.entity_id, mention.name) for mention in mentions if mention.subject}
        focus = tuple(phrase for phrase in _FOCUS_PHRASES if phrase in query)
        if not signals and not mentioned and not subjects and not focus:
            return RetrievalResult(())
        requested_stars = _requested_stars(query)
        bound_stars = _bound_stars(query, mentions) if requested_stars else {}
        missing = []
        for entity_id, stars in bound_stars.items():
            available = {
                entry.chunk.stars
                for entry in indexed
                if entry.chunk.entity_id == entity_id and entry.chunk.stars is not None
            }
            if available and not stars <= available:
                name = next(
                    entry.chunk.entity_names[0]
                    for entry in indexed
                    if entry.chunk.entity_id == entity_id
                )
                missing.append(
                    f"{name}：缺少所问的"
                    f"{'、'.join(str(s) for s in sorted(stars - available))}星数值"
                )
        if missing:
            return RetrievalResult((), missing_conditions=tuple(missing))
        engine_values = bool(requested_stars) or any(
            word in query
            for word in (
                "多少",
                "几吨",
                "多重",
                "数值",
                "上限",
                "下限",
                "改满",
                "总载重",
                "净载重",
                "基础载重",
                "各星",
                "不同星",
                "逐星",
                "几星",
            )
        )
        acquisition_query = any(word in query for word in ("获取", "获得", "哪里", "几星", "奖励"))
        reference_query = acquisition_query or any(
            word in query for word in ("掉落", "赏金首", "怪物", "出处", "谁掉")
        )
        guide_query = any(word in query for word in ("流程", "主线", "攻略", "通关"))
        ranked: list[tuple[float, EvidenceChunk]] = []
        for entry in indexed:
            chunk = entry.chunk
            exact = chunk.entity_id in mentioned
            local_exact = any((chunk.entity_id, name) in local_names for name in entry.subjects)
            if (
                subjects
                and chunk.entity_id in subjects
                and not local_exact
                and chunk.category in {"jobs", "vehicles"}
                and not any(
                    word in query
                    for word in ("主职业", "副职业规则", "职业通则", "驾驶等级", "成长")
                )
                and not (
                    chunk.category == "vehicles"
                    and any(
                        word in query for word in ("获取", "获得", "改造", "升级", "强化", "价格")
                    )
                )
            ):
                continue
            if subjects and chunk.entity_id in subjects and entry.subjects and not local_exact:
                continue
            if (
                mentioned
                and not exact
                and not local_exact
                and not (guide_query and chunk.category == "guides")
            ):
                continue
            if (
                mentioned
                and not exact
                and chunk.category == "wanted-monsters"
                and not reference_query
            ):
                continue
            if not mentioned and subjects and chunk.entity_id not in subjects:
                continue
            entity_stars = bound_stars.get(
                chunk.entity_id, requested_stars if len(mentioned) <= 1 else set()
            )
            if entity_stars and chunk.stars is not None and chunk.stars not in entity_stars:
                continue
            if chunk.entity_id.startswith("equipment:engine-"):
                if chunk.id.endswith(":facts"):
                    continue
                if chunk.id.endswith(":rules") and engine_values:
                    continue
                if chunk.stars is not None and not engine_values:
                    continue
                if chunk.id.endswith(":acquisition") and not acquisition_query:
                    continue
                if chunk.id.endswith(":upgrade") and not any(
                    word in query for word in ("价格", "钱", "费用", "强化", "升级")
                ):
                    continue
            hits = terms & entry.terms
            signal_hits = {
                term
                for term in signals & entry.terms
                if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", term) is None
            }
            focus_hits = sum(phrase in entry.body for phrase in focus)
            if (
                not exact
                and not local_exact
                and not focus_hits
                and not (signals & entry.title_terms)
            ):
                continue
            long_hit = any(len(term) >= 3 and not term.isdecimal() for term in signal_hits)
            if (
                not exact
                and not local_exact
                and len(signal_hits) < 2
                and not focus_hits
                and not long_hit
            ):
                continue
            score = sum(weights[term] for term in hits)
            score += 3 * sum(weights[term] for term in terms & entry.title_terms)
            score += 160 * exact + 100 * local_exact + 8 * focus_hits
            if entity_stars and chunk.stars is not None:
                score += 35 if chunk.stars in entity_stars else -45
            if chunk.category == "vehicles" and any(
                word in query for word in ("战车", "底盘", "双引擎", "双c装置")
            ):
                score += 12
            if chunk.category == "guides" and guide_query:
                score += 160
            if chunk.category == "jobs" and any(word in query for word in ("职业", "技能")):
                score += 8
            ranked.append((score, chunk))
        ranked.sort(key=lambda item: (-item[0], item[1].id))
        groups: dict[str, list[EvidenceChunk]] = defaultdict(list)
        for _, chunk in ranked:
            groups[chunk.entity_id].append(chunk)
        # 先各取一条，再回到同一实体补充证据，比较问题不会被单条长记录占满。
        per_entity = limit if len(groups) == 1 else max(2, min(4, limit // max(1, len(mentioned))))
        selected: list[EvidenceChunk] = []
        used = 0
        omitted = False
        for round_index in range(per_entity):
            for candidates in groups.values():
                if round_index >= len(candidates):
                    continue
                chunk = candidates[round_index]
                size = len(chunk.render(len(selected) + 1)) + (2 if selected else 0)
                if len(selected) >= limit or used + size > max_context_chars:
                    omitted = True
                    continue
                selected.append(chunk)
                used += size
        omitted = omitted or len(selected) < len(ranked)
        return RetrievalResult(tuple(selected), omitted)


def get_evidence_retriever() -> EvidenceRetriever:
    """问答服务只依赖统一检索契约。"""
    return LexicalEvidenceRetriever()
