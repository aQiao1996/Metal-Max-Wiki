import { describe, expect, it } from 'vitest'

import type { EquipmentEntry } from '@/types/equipment'

import {
  buildEquipmentDetailAttributes,
  buildEquipmentReturnHref,
  equipmentIssueLabels,
  equipmentNameSourceLabels,
} from './equipment-detail'

function makeEntry(
  overrides: Partial<Pick<EquipmentEntry, 'kind' | 'type' | 'attributes'>> = {},
): EquipmentEntry {
  return {
    id: 'test-equipment-aaaaaaaaaa',
    game: 'mm2r',
    target_version: '0.99',
    domain: 'equipment',
    kind: 'human_weapon',
    names: {
      ja: 'テスト装備',
      zh_09: '测试装备',
      zh_099: null,
      aliases: [],
    },
    attributes: {},
    version_scope: ['mm2r-jp'],
    verification_status: 'compatible_candidate',
    source_refs: [
      {
        source_id: 'test-source',
        target_id: 'test-target',
        source_url: 'https://example.com/equipment',
        retrieved_at: '2026-10-13T10:00:00+08:00',
        content_hash: `sha256:${'a'.repeat(64)}`,
        table_index: 0,
        row_index: 0,
      },
    ],
    source_spans: [],
    issues: [],
    asset_refs: [],
    type: 'human-weapon',
    name: '测试装备',
    nameSource: 'zh_09',
    searchText: '测试装备 テスト装備',
    ...overrides,
  }
}

describe('equipment detail', () => {
  it('保留数值 0、忽略缺失属性并转换职业装备标记', () => {
    const entry = makeEntry({
      attributes: {
        attack_raw: 0,
        range_raw: '1体',
        additional_raw: '追加伤害',
        hunter_raw: '○',
        mechanic_raw: '-',
        soldier_raw: '特例',
      },
    })

    expect(buildEquipmentDetailAttributes(entry)).toEqual([
      { label: '攻击力', value: '0' },
      { label: '范围', value: '1体' },
      { label: '追加效果', value: '追加伤害' },
      { label: '猎人', value: '可装备' },
      { label: '机械师', value: '不可装备' },
      { label: '战士', value: '特例' },
    ])
  })

  it('主炮属性按详情页顺序输出且不混入职业字段', () => {
    const entry = makeEntry({
      kind: 'main_cannon',
      type: 'main-cannon',
      attributes: {
        attack_raw: '500',
        defense_raw: '12',
        weight_raw: '3.20t',
        hunter_raw: '○',
        rarity_raw: '★★',
      },
    })

    expect(buildEquipmentDetailAttributes(entry)).toEqual([
      { label: '攻击力', value: '500' },
      { label: '防御力', value: '12' },
      { label: '重量', value: '3.20t' },
      { label: '稀有度', value: '★★' },
    ])
  })

  it('名称来源和已知问题使用固定中文文案', () => {
    expect(equipmentNameSourceLabels).toMatchObject({
      zh_099: '0.99 实机名称',
      zh_09: '0.9 系汉化名称',
      ja: '日文原名',
    })
    expect(equipmentIssueLabels).toMatchObject({
      missing_japanese_name: '来源缺少日文原名',
      ambiguous_same_source_name: '同一来源存在重名记录',
      source_merged_cell: '原始表格包含跨列单元格',
    })
    expect(equipmentIssueLabels.unknown_issue ?? 'unknown_issue').toBe(
      'unknown_issue',
    )
  })

  it('从嵌套查询串重建固定的站内返回地址', () => {
    expect(
      buildEquipmentReturnHref(
        'mm2r-099',
        'type=main-cannon&q=%E7%82%AE&sort=weight-asc&profession=hunter',
      ),
    ).toBe(
      '/v/mm2r-099/wiki/equipment?type=main-cannon&q=%E7%82%AE&sort=weight-asc',
    )
  })

  it('数组只取首项，缺失或外部地址输入均收敛到默认分类', () => {
    expect(
      buildEquipmentReturnHref('mm2r-099', [
        'type=human-weapon&profession=soldier',
        'type=main-cannon',
      ]),
    ).toBe('/v/mm2r-099/wiki/equipment?type=human-weapon&profession=soldier')
    expect(buildEquipmentReturnHref('mm2r-099')).toBe(
      '/v/mm2r-099/wiki/equipment?type=human-weapon',
    )
    expect(
      buildEquipmentReturnHref(
        'mm2r-099',
        'https://evil.example/path?type=main-cannon&sort=weight-asc',
      ),
    ).toBe('/v/mm2r-099/wiki/equipment?type=human-weapon')
  })
})
