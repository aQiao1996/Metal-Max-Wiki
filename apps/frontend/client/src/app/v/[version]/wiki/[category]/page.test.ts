import { describe, expect, it } from 'vitest'

import { legacyEquipmentCategories } from '@/config/equipment-types'

import CategoryPage from './page'

function makeProps(version: string, category: string) {
  return {
    params: Promise.resolve({ version, category }),
  }
}

describe('legacy equipment category page', () => {
  it.each(
    legacyEquipmentCategories.map(
      ({ categorySlug, typeId }) => [categorySlug, typeId] as const,
    ),
  )('将旧分类 %s 重定向装备百科的 %s 筛选', async (category, type) => {
    await expect(
      CategoryPage(makeProps('mm2r-099', category)),
    ).rejects.toMatchObject({
      digest: `NEXT_REDIRECT;replace;/v/mm2r-099/wiki/equipment?type=${type};307;`,
    })
  })

  it('无效版本在判断旧分类前先返回 404', async () => {
    await expect(
      CategoryPage(makeProps('missing-version', 'main-cannons')),
    ).rejects.toMatchObject({
      digest: 'NEXT_HTTP_ERROR_FALLBACK;404',
    })
  })

  it.each(['toString', 'constructor', '__proto__'])(
    '原型属性名 %s 不能命中旧分类重定向',
    async (category) => {
      await expect(
        CategoryPage(makeProps('mm2r-099', category)),
      ).rejects.toMatchObject({
        digest: 'NEXT_HTTP_ERROR_FALLBACK;404',
      })
    },
  )
})
