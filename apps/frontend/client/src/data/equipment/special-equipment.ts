const elements: Readonly<Record<string, string>> = {
  通常: '普通',
  火炎: '火焰',
  冷気: '冷气',
  電気: '电气',
  電撃: '电气',
  音波: '音波',
  ビーム: '光束',
  ガス: '毒气',
  'ビーム(+冷気)': '光束（附加冷气）',
}

/** 翻译固定术语，保留未知原文和“次攻击／连射”的区别。 */
export function formatSpecialEquipmentValue(
  key: string,
  value: string | number,
): string {
  const text = String(value)
  if (key === 'element_raw') return elements[text] ?? text
  if (key === 'range_raw') {
    return text
      .replaceAll('連射', '连射')
      .replaceAll('回', '次攻击')
      .replaceAll('迎撃', '迎击')
      .replaceAll('円範囲小', '小圆形')
      .replaceAll('円範囲大', '大圆形')
      .replaceAll('扇範囲小', '小扇形')
      .replaceAll('扇範囲大', '大扇形')
      .replaceAll('貫通小', '小范围贯穿')
      .replaceAll('貫通大', '大范围贯穿')
      .replaceAll('1体', '单体')
  }
  if (key === 'rarity_raw') {
    if (text === '-') return '无星'
    if (/^★{1,3}$/.test(text)) return `${text.length} 星固定`
    if (/^☆{1,3}$/.test(text)) return `0～${text.length} 星`
  }
  return text
}
