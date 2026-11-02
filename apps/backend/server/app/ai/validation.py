import re
from decimal import Decimal

from app.ai.evidence import EvidenceChunk
from app.core.errors import BusinessError

_CLAUSES = re.compile(r"[，,；;。！？!?\n]|然而|但是|可是|而且|并且|因为|所以|因此|但|且")


def _figures(text: str) -> set[Decimal]:
    text = re.sub(r"\[[0-9]+\]", "", text)
    text = re.sub(r"(?m)^\s*(?:[-*]\s*)?[0-9]+[.、)](?![0-9])\s*", "", text)
    return {
        Decimal(value.replace(",", ""))
        for value in re.findall(r"[0-9]+(?:,[0-9]{3})*(?:\.[0-9]+)?", text)
    }


def _uncertain_proposition(before: str, after: str) -> bool:
    # 否定必须修饰判断命题，不能由同句里无关的“不能相加”豁免肯定断言。
    denied = re.search(r"(?:不(?:完全|尽)?|并非|不是|未必|没有|是否(?:为|是|属于)?)$", before)
    unavailable = re.search(
        r"(?:不能|不应|不可|无法|未能)(?:直接)?(?:认为|断言|认定|确认|推断|确定|判断|证明|证实|肯定|说).{0,12}$|"
        r"(?:不能|不应|不可|无法)(?:把|将).{0,8}(?:视为|当作|看作|说成|认作)$|"
        r"(?:未|尚未)(?:说明|记载|证实|确定|证明|确认).{0,12}$|"
        r"(?:没有|尚无|无)证据(?:表明|证明|说明|支持|显示).{0,12}$",
        before,
    )
    unknown = re.match(
        r"(?:的(?:可能性|结论|说法)|性)?"
        r"(?:(?:尚未|未被|未经|未|仍未)(?:证实|证明|确认|确定|说明|记载)|"
        r"未知|不明|不确定|无法确定|尚不明确)",
        after.lstrip(),
    )
    return denied is not None or unavailable is not None or unknown is not None


def validate_factual_answer(answer: str, chunks: tuple[EvidenceChunk, ...]) -> None:
    """拒绝资料外数字、冲突反述和独立概率断言；数字追溯不等于算术或语义证明。"""
    source_text = "\n".join(f"{chunk.title}\n{chunk.text}" for chunk in chunks)
    if not _figures(answer) <= _figures(source_text) | {Decimal("0.99")}:
        raise BusinessError(502, "模型回答出现资料中未提供的数字，请缩小问题范围后重试")
    if "来源记载冲突" in source_text:
        for clause in _CLAUSES.split(answer):
            for match in re.finditer(r"一致", clause):
                if not _uncertain_proposition(clause[: match.start()], clause[match.end() :]):
                    raise BusinessError(502, "模型把明确的来源冲突说成一致，请重试")
    if not any(chunk.category == "wanted-monsters" for chunk in chunks):
        return
    assertion = re.compile(
        r"独立概率|相互独立|独立事件|统计独立|概率(?:是|为|均|各自|彼此)*独立|"
        r"槽(?:位)?(?:是|为|均|都|各自|彼此|相互)*独立|独立(?:判定|抽取)"
    )
    for clause in _CLAUSES.split(answer):
        for match in assertion.finditer(clause):
            if not _uncertain_proposition(clause[: match.start()], clause[match.end() :]):
                raise BusinessError(502, "模型将未收录的槽位独立性说成确定事实，请重试")
