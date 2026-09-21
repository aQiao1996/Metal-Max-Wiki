import type {
  WikiCategory,
  WikiCategorySlug,
  WikiEntityDetail,
} from '@/types/wiki'

export const wikiCategories = [
  {
    slug: 'vehicles',
    label: '战车',
    shortLabel: '战车',
    description: '车体、改造分支与战车特性',
    index: '01',
  },
  {
    slug: 'main-cannons',
    label: '主炮',
    shortLabel: '主炮',
    description: '单发、连射与特殊炮弹资料',
    index: '02',
  },
  {
    slug: 'sub-guns',
    label: '副炮',
    shortLabel: '副炮',
    description: '副炮属性、攻击范围与适用场景',
    index: '03',
  },
  {
    slug: 'special-equipment',
    label: 'S-E',
    shortLabel: 'S-E',
    description: '特殊装备、连射方式与隐藏效果',
    index: '04',
  },
  {
    slug: 'c-units',
    label: 'C装置',
    shortLabel: 'C装置',
    description: '特性、载重与火力流派配置',
    index: '05',
  },
  {
    slug: 'engines',
    label: '引擎',
    shortLabel: '引擎',
    description: '载重、改造路线与获取来源',
    index: '06',
  },
  {
    slug: 'wanted-monsters',
    label: '赏金首',
    shortLabel: '赏金首',
    description: '位置、触发条件与掉落校对',
    index: '07',
  },
  {
    slug: 'jobs',
    label: '职业与技能',
    shortLabel: '职业',
    description: '主副职业、成长方向与技能用途',
    index: '08',
  },
] as const satisfies readonly WikiCategory[]

export const wikiEntities = [
  {
    slug: 'red-wolf',
    category: 'vehicles',
    name: '红狼战车',
    aliases: ['红狼', 'R狼'],
    summary: '以主炮输出见长的经典战车，需要结合版本核对改造分支。',
    tags: ['战车', '主炮流', '改造'],
    verification: 'pending',
    image: null,
    attributes: [
      { label: '资料版本', value: '2R 0.99 汉化版' },
      { label: '定位', value: '主炮输出' },
      { label: '校对状态', value: '改造名称与数值待实机核对' },
    ],
    sections: [
      {
        id: 'overview',
        title: '使用思路',
        paragraphs: [
          '页面将保留不同改造路线的差异，最终数值以 0.99 版实机核对结果为准。',
        ],
      },
      {
        id: 'build',
        title: '配装方向',
        paragraphs: [
          '优先呈现主炮、C 装置、引擎和底盘之间的取舍，不在资料未核验时填写推测数值。',
        ],
      },
    ],
    relatedSlugs: ['universe-cannon', 'ddt-rain'],
    sources: [
      {
        title: '游戏内改造界面',
        note: '需使用 0.99 汉化版存档复核',
        href: null,
        status: 'pending',
      },
    ],
  },
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
    relatedSlugs: ['red-wolf'],
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
    relatedSlugs: ['red-wolf'],
    sources: [
      {
        title: '游戏内 S-E 说明',
        note: '0.99 版本数据待录入',
        href: null,
        status: 'pending',
      },
    ],
  },
  {
    slug: 'sand-shark',
    category: 'wanted-monsters',
    name: '砂蛟',
    aliases: [],
    summary: '赏金首条目将统一收录位置、触发条件和掉落来源。',
    tags: ['赏金首', '掉落'],
    verification: 'pending',
    image: null,
    attributes: [
      { label: '类型', value: '赏金首' },
      { label: '位置', value: '待地图素材校对' },
      { label: '掉落率', value: '待 0.99 版本数据核验' },
    ],
    sections: [
      {
        id: 'drops',
        title: '掉落记录',
        paragraphs: [
          '掉落物、判定次数和概率将保持分开字段，重点装备会在数据核验后标记。',
        ],
      },
    ],
    relatedSlugs: [],
    sources: [
      {
        title: '0.99 版赏金首记录',
        note: '位置与掉落数据待校对',
        href: null,
        status: 'pending',
      },
    ],
  },
] as const satisfies readonly WikiEntityDetail[]

export const wikiCategoriesBySlug = new Map<WikiCategorySlug, WikiCategory>(
  wikiCategories.map((category) => [category.slug, category]),
)
