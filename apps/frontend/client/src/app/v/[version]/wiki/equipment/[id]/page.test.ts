import { describe, expect, it } from 'vitest'

import { getEquipmentEntries } from '@/data/equipment/catalog'

import { dynamicParams, generateMetadata, generateStaticParams } from './page'

function makeProps(version: string, id: string) {
  return {
    params: Promise.resolve({ version, id }),
    searchParams: Promise.resolve({}),
  }
}

describe('equipment detail page', () => {
  const entry = getEquipmentEntries()[0]

  if (entry === undefined) {
    throw new Error('期望装备目录至少包含一条记录')
  }

  it('只允许已收录的 0.99 装备静态参数', () => {
    const params = generateStaticParams()

    expect(dynamicParams).toBe(false)
    expect(params).toHaveLength(407)
    expect(new Set(params.map(({ id }) => id)).size).toBe(407)
    expect(params.every(({ version }) => version === 'mm2r-099')).toBe(true)
  })

  it('生成不含查询参数的固定站点 canonical', async () => {
    await expect(
      generateMetadata(makeProps('mm2r-099', entry.id)),
    ).resolves.toEqual({
      title: `${entry.name}｜装备百科`,
      alternates: {
        canonical: `https://mm.yangyunqiao.top/v/mm2r-099/wiki/equipment/${entry.id}`,
      },
    })
  })

  it.each([
    ['missing-version', entry.id],
    ['mm2r-nex', entry.id],
    ['mm2r-099', 'missing-equipment-id'],
  ])('无效版本或装备触发 404：%s / %s', async (version, id) => {
    await expect(
      generateMetadata(makeProps(version, id)),
    ).rejects.toMatchObject({
      digest: 'NEXT_HTTP_ERROR_FALLBACK;404',
    })
  })
})
