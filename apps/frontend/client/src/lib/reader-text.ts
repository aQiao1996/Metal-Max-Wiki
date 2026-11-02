const metadataClauses = [
  ['，全部source_only，未以0.99实机逐项验证', ''],
  ['；全部source_only，未在0.99汉化实机逐项核验', ''],
  ['，未与0.99汉化游戏逐项核验', ''],
  ['，尚未在0.99实机核验', ''],
  ['，未在0.99实机核验', ''],
  ['；不代表0.99汉化实机名称或已核验的0.99机制', ''],
  [
    '，译名、空白、问号和报酬条件均不能自动当作已核验的0.99资料',
    '，译名、空白、问号和报酬条件沿用各自来源记录',
  ],
  ['；效果尚待0.99实机核验', ''],
  ['，不把可反复使用或一次性标为0.99已核验', ''],
  ['；未经0.99实机验证', ''],
  [' · 0.99未验证', ''],
  ['同星级来源数值差异（尚待核对）', '同星级来源数值差异'],
] as const

/** 只隐藏已确认的状态元数据，保留来源差异与游戏条件正文。 */
export function formatReaderText(value: string): string {
  return metadataClauses.reduce(
    (text, [clause, replacement]) => text.replaceAll(clause, replacement),
    value.replace(/^名称核验范围：[^\n]*\n?/u, ''),
  )
}
