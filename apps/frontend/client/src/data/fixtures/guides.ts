import type { GuideDetail } from '@/types/wiki'

export const guides = [
  {
    slug: 'vehicle-build-basics',
    title: '战车改造前的准备',
    summary:
      '先确认版本、改造路线和负重余量，再决定主炮、S-E 与 C 装置的分配。',
    sectionCount: 3,
    status: 'published',
    sections: [
      {
        id: 'version',
        title: '先确认版本',
        paragraphs: [
          '改造名称、分支和装备数值可能因汉化版或民间改版不同。本站使用地址中的版本标识隔离资料。',
        ],
      },
      {
        id: 'role',
        title: '确定战车定位',
        paragraphs: [
          '一辆车先确定主要输出方式，再围绕底盘特性选择装备，可以减少负重和穴位冲突。',
        ],
        table: {
          headers: ['检查项', '记录内容'],
          rows: [
            ['底盘', '当前改造名称与特性'],
            ['装备', '主要输出方式与弹仓需求'],
            ['负重', '引擎载重与装甲余量'],
          ],
        },
      },
      {
        id: 'record',
        title: '保留改造记录',
        paragraphs: [
          '在不可逆改造前保留存档，并记下分支名称。后续资料校对也会以这些实机记录为准。',
        ],
      },
    ],
    sources: [
      {
        title: '游戏内改造界面',
        note: '页面结构示例，具体分支待实机录入',
        href: null,
        status: 'pending',
      },
    ],
  },
  {
    slug: 'wanted-drop-recording',
    title: '赏金首掉落的记录方法',
    summary: '区分掉落物、判定次数和重复实测结果，便于后续核对。',
    sectionCount: 2,
    status: 'draft',
    sections: [
      {
        id: 'fields',
        title: '记录字段',
        paragraphs: [
          '每次战斗应记录版本、赏金首、实际掉落物和是否使用改变掉落的手段。',
        ],
      },
      {
        id: 'publish',
        title: '发布前校对',
        paragraphs: ['概率数值不从单次经验推测，需要保留来源和样本说明。'],
      },
    ],
    sources: [],
  },
] as const satisfies readonly GuideDetail[]
