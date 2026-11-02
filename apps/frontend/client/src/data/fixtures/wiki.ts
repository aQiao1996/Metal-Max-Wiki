import type {
  WikiCategory,
  WikiCategorySlug,
  WikiEntityDetail,
} from '@/types/wiki'
import {
  legacyEquipmentCategories,
  type LegacyEquipmentCategorySlug,
} from '@/config/equipment-types'

export const wikiCategories = [
  {
    slug: 'vehicles',
    label: '战车',
    shortLabel: '战车',
    description: '车体、改造分支与战车特性',
    index: '01',
  },
  {
    slug: 'equipment',
    label: '装备',
    shortLabel: '装备',
    description: '人类武器、主炮、副炮、S-E、C装置与引擎',
    index: '02',
  },
  {
    slug: 'wanted-monsters',
    label: '赏金首',
    shortLabel: '赏金首',
    description: '位置、触发条件与掉落校对',
    index: '03',
  },
  {
    slug: 'jobs',
    label: '职业与技能',
    shortLabel: '职业',
    description: '主副职业、成长方向与技能用途',
    index: '04',
  },
  {
    slug: 'items',
    label: '道具',
    shortLabel: '道具',
    description: '道具用途、获取地点、特殊炮弹与 LOVE 配方',
    index: '05',
  },
  {
    slug: 'quests',
    label: '任务与委托',
    shortLabel: '任务',
    description: '接取条件、完成步骤、报酬与错过条件',
    index: '06',
  },
] as const satisfies readonly WikiCategory[]

const legacyWikiCategoryMetadata = {
  'main-cannons': {
    label: '主炮',
    shortLabel: '主炮',
    description: '单发、连射与特殊炮弹资料',
    index: '02',
  },
  'sub-guns': {
    label: '副炮',
    shortLabel: '副炮',
    description: '副炮属性、攻击范围与适用场景',
    index: '03',
  },
  'special-equipment': {
    label: 'S-E',
    shortLabel: 'S-E',
    description: '特殊装备、连射方式与隐藏效果',
    index: '04',
  },
  'c-units': {
    label: 'C装置',
    shortLabel: 'C装置',
    description: '特性、载重与火力流派配置',
    index: '05',
  },
  engines: {
    label: '引擎',
    shortLabel: '引擎',
    description: '载重、改造路线与获取来源',
    index: '06',
  },
} as const satisfies Record<
  LegacyEquipmentCategorySlug,
  Omit<WikiCategory, 'slug'>
>

const legacyWikiCategories = legacyEquipmentCategories.map(
  ({ categorySlug }): WikiCategory => ({
    slug: categorySlug,
    ...legacyWikiCategoryMetadata[categorySlug],
  }),
)

export const wikiEntities = [
  {
    slug: 'universe-cannon',
    category: 'main-cannons',
    name: '宇宙炮',
    aliases: [],
    summary: '具有成长机制的主炮，喂养与属性结果需按版本单独记录。',
    tags: ['主炮', '成长武器'],
    verification: 'pending',
    image: null,
    attributes: [
      { label: '类型', value: '成长型主炮' },
      { label: '属性', value: '待实机核对' },
      { label: '成长结果', value: '将分版本记录' },
    ],
    sections: [
      {
        id: 'growth',
        title: '成长记录',
        paragraphs: [
          '后续数据结构会保留喂养素材、结果与验证次数，方便区分随机波动和固定规则。',
        ],
      },
    ],
    relatedSlugs: [],
    sources: [
      {
        title: '游戏内武器界面',
        note: '属性与喂养结果待实机录入',
        href: null,
        status: 'pending',
      },
    ],
  },
  {
    slug: 'ddt-rain',
    category: 'special-equipment',
    name: 'DDT 暴雨',
    aliases: ['DDT暴雨'],
    summary: '属于 S-E 资料中需要重点核对攻击方式与特殊效果的条目。',
    tags: ['S-E', '攻击方式'],
    verification: 'pending',
    image: null,
    attributes: [
      { label: '类型', value: 'S-E' },
      { label: '攻击方式', value: '待实机核对' },
      { label: '特殊效果', value: '待实机核对' },
    ],
    sections: [
      {
        id: 'verification',
        title: '核对要点',
        paragraphs: [
          '需要分开记录界面说明、实际攻击段数和属性效果，避免把玩家经验当作固定数值。',
        ],
      },
    ],
    relatedSlugs: [],
    sources: [
      {
        title: '游戏内 S-E 说明',
        note: '0.99 版本数据待录入',
        href: null,
        status: 'pending',
      },
    ],
  },
] as const satisfies readonly WikiEntityDetail[]

export const wikiCategoriesBySlug = new Map<WikiCategorySlug, WikiCategory>(
  [...wikiCategories, ...legacyWikiCategories].map(
    (category): [WikiCategorySlug, WikiCategory] => [category.slug, category],
  ),
)
