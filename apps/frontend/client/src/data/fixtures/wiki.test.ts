import { describe, expect, it } from 'vitest'

import { legacyEquipmentCategories } from '@/config/equipment-types'
import { wikiCategorySlugs } from '@/types/wiki'

import { wikiCategories, wikiCategoriesBySlug } from './wiki'

describe('wiki categories', () => {
  it('公开分类展示固定的六个入口', () => {
    expect(wikiCategories.map(({ slug, index }) => ({ slug, index }))).toEqual([
      { slug: 'vehicles', index: '01' },
      { slug: 'equipment', index: '02' },
      { slug: 'wanted-monsters', index: '03' },
      { slug: 'jobs', index: '04' },
      { slug: 'items', index: '05' },
      { slug: 'quests', index: '06' },
    ])
  })

  it('装备入口覆盖人类武器和全部战车装备类型', () => {
    expect(wikiCategoriesBySlug.get('equipment')).toMatchObject({
      label: '装备',
      shortLabel: '装备',
      description: '人类武器、主炮、副炮、S-E、C装置与引擎',
    })
    expect(wikiCategorySlugs).toContain('equipment')
  })

  it('保留旧装备分类元数据用于旧详情和 fixture 解析', () => {
    const legacyEquipmentCategorySlugs = legacyEquipmentCategories.map(
      ({ categorySlug }) => categorySlug,
    )

    expect(
      legacyEquipmentCategorySlugs.map(
        (slug) => wikiCategoriesBySlug.get(slug)?.slug,
      ),
    ).toEqual(legacyEquipmentCategorySlugs)
    expect(legacyEquipmentCategorySlugs).toHaveLength(5)
    expect(
      legacyEquipmentCategorySlugs.every((slug) =>
        wikiCategorySlugs.includes(slug),
      ),
    ).toBe(true)
  })
})
