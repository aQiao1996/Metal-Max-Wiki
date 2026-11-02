/** 将接口驼峰字段还原为资料快照字段，随后交给 Schema 校验。 */
export function restoreSourceKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(restoreSourceKeys)
  if (typeof value !== 'object' || value === null) return value
  const entries: [string, unknown][] = Object.entries(value)
  return Object.fromEntries(
    entries.map(([key, item]) => [
      key === 'zh09'
        ? 'zh_09'
        : key === 'zh099'
          ? 'zh_099'
          : key.replace(/[A-Z]/g, (letter) => `_${letter.toLowerCase()}`),
      restoreSourceKeys(item),
    ]),
  )
}
