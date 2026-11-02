import { describe, expect, expectTypeOf, it } from 'vitest'
import { ZodError } from 'zod'

import {
  getEquipmentCatalog,
  getEquipmentEntry,
  getEquipmentEntries,
  parseEquipmentDataset,
  toEquipmentEntry,
} from './catalog'
import type { RawEquipmentRecord } from './schema'

const sourceHash = `sha256:${'a'.repeat(64)}`

function createRecord(
  id: string,
  names: RawEquipmentRecord['names'] = {
    ja: 'テスト武器',
    zh_09: null,
    zh_099: null,
    aliases: [],
  },
): RawEquipmentRecord {
  return {
    id,
    game: 'mm2r',
    target_version: '0.99',
    domain: 'equipment',
    kind: 'human_weapon',
    names,
    attributes: {
      attack: 1,
    },
    version_scope: ['mm2r-jp'],
    verification_status: 'compatible_candidate',
    source_refs: [
      {
        source_id: 'test-source',
        target_id: 'test-target',
        source_url: 'https://example.com/equipment',
        retrieved_at: '2026-10-13T10:00:00+08:00',
        content_hash: sourceHash,
        table_index: 0,
        row_index: 0,
      },
    ],
    source_spans: [
      {
        source_id: 'test-source',
        target_id: 'test-target',
        table_index: 0,
        row_index: 0,
        start_header: '名称',
        end_header: '攻击力',
        value: 'テスト武器',
      },
    ],
    issues: [],
    asset_refs: [],
  }
}

function createDataset(records: unknown[]) {
  return {
    schema_version: 1,
    game: 'mm2r',
    target_version: '0.99',
    domain: 'equipment',
    source_hashes: [sourceHash],
    records,
  }
}

describe('equipment catalog', () => {
  it('返回完整的装备目录', () => {
    const catalog = getEquipmentCatalog()

    expect(catalog).toHaveLength(287)
    expect(
      catalog.filter((record) => record.kind === 'human_weapon'),
    ).toHaveLength(55)
    expect(
      catalog.filter((record) => record.kind === 'main_cannon'),
    ).toHaveLength(95)
  })

  it('拒绝重复的稳定 ID', () => {
    const duplicateId = 'human-weapon-aaaaaaaaaa'

    expect(() =>
      parseEquipmentDataset(
        createDataset([createRecord(duplicateId), createRecord(duplicateId)]),
      ),
    ).toThrow(`装备数据包含重复 ID：${duplicateId}`)
  })

  it.each([
    'human-weapon/unsafe',
    'human-weapon?unsafe',
    'human-weapon-missinghash',
    'human-weapon-abcdefghi0',
    'human-weapon-abcdef01234',
  ])('拒绝不符合标准化契约的稳定 ID：%s', (invalidId) => {
    expect(() =>
      parseEquipmentDataset(createDataset([createRecord(invalidId)])),
    ).toThrow(ZodError)
  })

  it.each(['javascript:alert(1)', 'data:text/html,<h1>unsafe</h1>'])(
    '拒绝非 HTTP(S) 的来源地址：%s',
    (sourceUrl) => {
      const record = createRecord('unsafe-source-url-bbbbbbbbbb')
      record.source_refs[0] = {
        ...record.source_refs[0],
        source_url: sourceUrl,
      }

      try {
        parseEquipmentDataset(createDataset([record]))
        throw new Error('期望非法来源协议触发 ZodError')
      } catch (error) {
        expect(error).toBeInstanceOf(ZodError)
        if (!(error instanceof ZodError)) {
          throw error
        }

        expect(
          error.issues.some((issue) => issue.path.at(-1) === 'source_url'),
        ).toBe(true)
      }
    },
  )

  it('用 Zod 错误定位未知 kind', () => {
    try {
      parseEquipmentDataset(
        createDataset([
          { ...createRecord('unknown-kind-cccccccccc'), kind: 'unknown' },
        ]),
      )
      throw new Error('期望未知 kind 触发 ZodError')
    } catch (error) {
      expect(error).toBeInstanceOf(ZodError)
      if (!(error instanceof ZodError)) {
        throw error
      }

      expect(error.issues.some((issue) => issue.path.at(-1) === 'kind')).toBe(
        true,
      )
    }
  })

  it('运行时拒绝中间记录越级标记为 verified_0_99', () => {
    const record = createRecord('verified-status-dddddddddd')
    record.verification_status = 'verified_0_99'

    expect(() => parseEquipmentDataset(createDataset([record]))).toThrow(
      ZodError,
    )
    expectTypeOf<RawEquipmentRecord['verification_status']>().toEqualTypeOf<
      'source_only' | 'compatible_candidate' | 'verified_0_99'
    >()
  })

  it('拒绝没有来源引用的中间记录', () => {
    const record = createRecord('empty-source-refs-eeeeeeeeee')
    record.source_refs = []

    expect(() => parseEquipmentDataset(createDataset([record]))).toThrow(
      ZodError,
    )
  })

  it('优先使用 0.99 中文名', () => {
    const entry = toEquipmentEntry(
      createRecord('preferred-name-1111111111', {
        ja: 'テスト武器',
        zh_09: '0.9 中文名',
        zh_099: '0.99 中文名',
        aliases: [],
      }),
    )

    expect(entry.name).toBe('0.99 中文名')
    expect(entry.nameSource).toBe('zh_099')
  })

  it('0.99 中文名缺失时回退到 0.9 中文名', () => {
    const entry = toEquipmentEntry(
      createRecord('zh-09-fallback-2222222222', {
        ja: 'テスト武器',
        zh_09: '0.9 中文名',
        zh_099: null,
        aliases: [],
      }),
    )

    expect(entry.name).toBe('0.9 中文名')
    expect(entry.nameSource).toBe('zh_09')
  })

  it('两个中文名均缺失时回退到日文名', () => {
    const entry = toEquipmentEntry(
      createRecord('ja-fallback-3333333333', {
        ja: 'テスト武器',
        zh_09: null,
        zh_099: null,
        aliases: [],
      }),
    )

    expect(entry.name).toBe('テスト武器')
    expect(entry.nameSource).toBe('ja')
  })

  it('所有名称均缺失时报告记录 ID', () => {
    const id = 'missing-display-name-4444444444'

    expect(() =>
      toEquipmentEntry(
        createRecord(id, {
          ja: null,
          zh_09: null,
          zh_099: null,
          aliases: [],
        }),
      ),
    ).toThrow(`装备记录缺少可显示名称：${id}`)
  })

  it('生成仅包含指定名称和原始文字字段的搜索文本', () => {
    const record = createRecord('search-text-5555555555', {
      ja: 'Japanese Name',
      zh_09: '0.9 Name',
      zh_099: 'Preferred Name',
      aliases: ['Alias One', 'Alias Two'],
    })
    record.attributes = {
      ...record.attributes,
      acquisition_raw: 'Shop Name',
      additional_raw: 'Break Parts',
      notes_raw: 'Rare Drop',
      attack_raw: 'Do Not Include',
    }

    const entry = toEquipmentEntry(record)

    expect(entry.searchText).toBe(
      [
        'Preferred Name',
        'Japanese Name',
        '0.9 Name',
        'Preferred Name',
        'Alias One',
        'Alias Two',
        'Shop Name',
        'Break Parts',
        'Rare Drop',
      ]
        .join(' ')
        .toLocaleLowerCase('zh-CN'),
    )
  })

  it('转换全部真实装备记录', () => {
    const entries = getEquipmentEntries()

    expect(entries).toHaveLength(287)
    expect(entries.every((entry) => entry.name.length > 0)).toBe(true)
    expect(
      entries.filter((entry) => entry.type === 'human-weapon'),
    ).toHaveLength(55)
    expect(
      entries.filter((entry) => entry.type === 'main-cannon'),
    ).toHaveLength(95)
  })

  it('按稳定 ID 查找装备条目', () => {
    const expectedEntry = getEquipmentEntries()[0]

    expect(expectedEntry).toBeDefined()
    if (expectedEntry === undefined) {
      throw new Error('期望装备目录至少包含一条记录')
    }

    expect(getEquipmentEntry(expectedEntry.id)).toBe(expectedEntry)
    expect(getEquipmentEntry('missing-equipment-id')).toBeUndefined()
  })
})
