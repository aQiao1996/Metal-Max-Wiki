import { describe, expect, it } from 'vitest'

import { getEquipmentEntries } from '@/data/equipment/catalog'
import type { EquipmentEntry, EquipmentQuery } from '@/types/equipment'

import {
  buildEquipmentSearch,
  filterEquipmentEntries,
  parseEquipmentQuery,
} from './equipment-query'

const testSourceRef = {
  source_id: 'test-source',
  target_id: 'test-target',
  source_url: 'https://example.com/equipment',
  retrieved_at: '2026-10-13T10:00:00+08:00',
  content_hash: `sha256:${'a'.repeat(64)}`,
  table_index: 0,
  row_index: 0,
} satisfies EquipmentEntry['source_refs'][number]

function makeEntry({
  id,
  name = id,
  type = 'human-weapon',
  searchText = name.toLocaleLowerCase('zh-CN'),
  attributes = {},
}: {
  id: string
  name?: string
  type?: EquipmentEntry['type']
  searchText?: string
  attributes?: EquipmentEntry['attributes']
}): EquipmentEntry {
  return {
    id,
    game: 'mm2r',
    target_version: '0.99',
    domain: 'equipment',
    kind: type === 'main-cannon' ? 'main_cannon' : 'human_weapon',
    names: {
      ja: name,
      zh_09: null,
      zh_099: null,
      aliases: [],
    },
    attributes,
    version_scope: ['mm2r-jp'],
    verification_status: 'compatible_candidate',
    source_refs: [testSourceRef],
    source_spans: [],
    issues: [],
    asset_refs: [],
    type,
    name,
    nameSource: 'ja',
    searchText,
  }
}

function makeQuery(overrides: Partial<EquipmentQuery> = {}): EquipmentQuery {
  return {
    type: 'human-weapon',
    q: '',
    sort: 'name-asc',
    element: '',
    trait: '',
    profession: '',
    ...overrides,
  }
}

describe('equipment query', () => {
  it('非法类型和该默认类型不允许的排序收敛为默认查询', () => {
    expect(
      parseEquipmentQuery({
        type: 'unknown',
        sort: 'weight-asc',
        profession: 'unknown',
      }),
    ).toEqual({
      type: 'human-weapon',
      q: '',
      sort: 'name-asc',
      element: '',
      trait: '',
      profession: '',
    })
  })

  it('组合搜索文本、属性和猎人职业筛选后按攻击力降序排列', () => {
    const entries = [
      makeEntry({
        id: 'matching-low-0000000001',
        name: '火焰枪',
        searchText: '火焰枪 flame',
        attributes: {
          attack: 120,
          element_raw: '火焰',
          hunter_raw: '○',
        },
      }),
      makeEntry({
        id: 'matching-high-0000000002',
        name: '烈焰炮',
        searchText: '烈焰炮 flame',
        attributes: {
          attack: 200,
          element_raw: '火焰',
          hunter_raw: '○',
        },
      }),
      makeEntry({
        id: 'wrong-profession-0000000003',
        searchText: 'flame',
        attributes: {
          attack: 300,
          element_raw: '火焰',
          hunter_raw: '-',
        },
      }),
      makeEntry({
        id: 'wrong-element-0000000004',
        searchText: 'flame',
        attributes: {
          attack: 400,
          element_raw: '通常',
          hunter_raw: '○',
        },
      }),
      makeEntry({
        id: 'wrong-type-0000000005',
        type: 'main-cannon',
        searchText: 'flame',
        attributes: {
          attack: 500,
          element_raw: '火焰',
          hunter_raw: '○',
        },
      }),
      makeEntry({
        id: 'wrong-search-0000000006',
        searchText: 'ice',
        attributes: {
          attack: 600,
          element_raw: '火焰',
          hunter_raw: '○',
        },
      }),
    ]

    const result = filterEquipmentEntries(
      entries,
      makeQuery({
        q: 'FLAME',
        sort: 'attack-desc',
        element: '火焰',
        profession: 'hunter',
      }),
    )

    expect(result.map((entry) => entry.id)).toEqual([
      'matching-high-0000000002',
      'matching-low-0000000001',
    ])
  })

  it('主炮查询清空职业并将不允许的排序回退到名称升序', () => {
    expect(
      parseEquipmentQuery({
        type: ['main-cannon', 'human-weapon'],
        q: ['  炮  ', 'ignored'],
        sort: 'unsupported',
        element: '  通常 ',
        profession: 'hunter',
      }),
    ).toEqual({
      type: 'main-cannon',
      q: '炮',
      sort: 'name-asc',
      element: '通常',
      trait: '',
      profession: '',
    })
  })

  it('只将非默认且非空的查询参数写入搜索串', () => {
    expect(
      buildEquipmentSearch(
        makeQuery({
          type: 'main-cannon',
          q: '炮',
          profession: 'hunter',
        }),
      ),
    ).toBe('type=main-cannon&q=%E7%82%AE')

    expect(
      buildEquipmentSearch(
        makeQuery({
          q: '枪',
          sort: 'attack-desc',
          element: '火焰',
          profession: 'soldier',
        }),
      ),
    ).toBe(
      'type=human-weapon&q=%E6%9E%AA&sort=attack-desc&element=%E7%81%AB%E7%84%B0&profession=soldier',
    )
  })

  it.each([
    {
      sort: 'attack-desc' as const,
      firstValue: 20,
      secondValue: 10,
    },
    { sort: 'price-asc' as const, firstValue: 10, secondValue: 20 },
    { sort: 'weight-asc' as const, firstValue: 10, secondValue: 20 },
  ])('$sort 将缺失数值放在有效值之后且不修改输入数组', (testCase) => {
    const numericKey = testCase.sort.split('-')[0]
    const entries = [
      makeEntry({ id: 'missing-0000000001', type: 'main-cannon' }),
      makeEntry({
        id: 'second-0000000002',
        type: 'main-cannon',
        attributes: { [numericKey]: testCase.secondValue },
      }),
      makeEntry({
        id: 'first-0000000003',
        type: 'main-cannon',
        attributes: { [numericKey]: testCase.firstValue },
      }),
    ]
    const originalOrder = entries.map((entry) => entry.id)

    const result = filterEquipmentEntries(
      entries,
      makeQuery({ type: 'main-cannon', sort: testCase.sort }),
    )

    expect(result).not.toBe(entries)
    expect(result.map((entry) => entry.id)).toEqual([
      'first-0000000003',
      'second-0000000002',
      'missing-0000000001',
    ])
    expect(entries.map((entry) => entry.id)).toEqual(originalOrder)
  })

  it('按真实主炮的数值或纯十进制原始重量整体升序排列', () => {
    const result = filterEquipmentEntries(
      getEquipmentEntries(),
      makeQuery({ type: 'main-cannon', sort: 'weight-asc' }),
    )
    const sortableWeights = result
      .map((entry) => {
        const numericWeight = entry.attributes.weight
        if (typeof numericWeight === 'number') {
          return numericWeight
        }

        const rawWeight = entry.attributes.weight_raw
        return typeof rawWeight === 'string' &&
          /^\d+(?:\.\d+)?$/.test(rawWeight)
          ? Number(rawWeight)
          : undefined
      })
      .filter((weight): weight is number => weight !== undefined)

    expect(sortableWeights).toHaveLength(94)
    expect(sortableWeights).toEqual([...sortableWeights].sort((a, b) => a - b))
    expect(
      result.findIndex(({ id }) => id === 'main-cannon-58325e818a'),
    ).toBeLessThan(
      result.findIndex(({ id }) => id === 'main-cannon-57c882824d'),
    )
  })

  it('优先数值字段且不把非纯十进制原始值当作排序数字', () => {
    const entries = [
      makeEntry({
        id: 'negative-integer-0000000008',
        type: 'main-cannon',
        attributes: { weight_raw: '-1' },
      }),
      makeEntry({
        id: 'negative-decimal-0000000009',
        type: 'main-cannon',
        attributes: { weight_raw: '-0.5' },
      }),
      makeEntry({
        id: 'infinity-0000000001',
        type: 'main-cannon',
        attributes: { weight_raw: '∞' },
      }),
      makeEntry({
        id: 'dash-0000000002',
        type: 'main-cannon',
        attributes: { weight_raw: '-' },
      }),
      makeEntry({
        id: 'unit-0000000003',
        type: 'main-cannon',
        attributes: { weight_raw: '3t' },
      }),
      makeEntry({
        id: 'mixed-0000000004',
        type: 'main-cannon',
        attributes: { weight_raw: '4.5 tons' },
      }),
      makeEntry({
        id: 'numeric-preferred-0000000005',
        type: 'main-cannon',
        attributes: { weight: 10, weight_raw: '0.1' },
      }),
      makeEntry({
        id: 'raw-integer-0000000006',
        type: 'main-cannon',
        attributes: { weight_raw: '2' },
      }),
      makeEntry({
        id: 'raw-decimal-0000000007',
        type: 'main-cannon',
        attributes: { weight_raw: '0.85' },
      }),
    ]

    const result = filterEquipmentEntries(
      entries,
      makeQuery({ type: 'main-cannon', sort: 'weight-asc' }),
    )

    expect(result.map((entry) => entry.id)).toEqual([
      'raw-decimal-0000000007',
      'raw-integer-0000000006',
      'numeric-preferred-0000000005',
      'negative-integer-0000000008',
      'negative-decimal-0000000009',
      'infinity-0000000001',
      'dash-0000000002',
      'unit-0000000003',
      'mixed-0000000004',
    ])
  })
})
