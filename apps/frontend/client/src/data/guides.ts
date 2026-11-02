import { cache } from 'react'
import { z } from 'zod'

import rawGuideDataset from '../../../../../data/interim/mm2r/0.99/guides.json'

import type { GameVersionSlug } from '@/config/game-versions'
import { guideSlugs } from '@/data/guide-routes'
import { serverRequest } from '@/lib/request/server'
import type { GuideSummary as HomeGuideSummary } from '@/types/wiki'

const slugSchema = z.string().regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/)
const contentHashSchema = z.string().regex(/^sha256:[0-9a-f]{64}$/)
export const guidePhaseIdSchema = z.enum([
  'opening',
  'ship-and-key',
  'dark-canal',
  'southern-gate',
  'bias-facility',
  'finale',
])
const guideKindSchema = z.enum(['main', 'preparation', 'optional'])
const verificationSchema = z.literal('source_only')
const guideSourceRefSchema = z
  .object({
    sourceId: z.string().min(1),
    targetId: z.string().min(1),
    sourceUrl: z.url(),
    retrievedAt: z.iso.datetime({ offset: true }),
    contentHash: contentHashSchema,
    tableIndex: z.number().int().nonnegative(),
    rowIndex: z.number().int().nonnegative(),
  })
  .strict()
const guidePhaseSchema = z
  .object({
    id: guidePhaseIdSchema,
    order: z.number().int().min(1).max(6),
    titleZh: z.string().min(1),
  })
  .strict()
const guideFactSchema = z
  .object({
    id: slugSchema,
    textZh: z.string().min(1),
    sourceKey: z.string().min(1),
    section: z.string().min(1),
    evidence: z.array(z.string().min(1)).min(1),
    rawValues: z.record(z.string(), z.string()),
    locator: z.string().min(1),
    sourceRef: guideSourceRefSchema,
    verificationStatus: verificationSchema,
  })
  .strict()
const guideBattleSchema = guideFactSchema.extend({
  requirement: z.enum(['mandatory', 'optional', 'scripted_loss']),
})
const guideDiagramSchema = z
  .object({
    id: slugSchema,
    titleZh: z.string().min(1),
    altZh: z.string().min(1),
    chapterIds: z.array(slugSchema).min(1),
    repoRelativePath: z
      .string()
      .regex(
        /^data\/raw\/mm2r\/0\.99\/guides\/diagrams\/[a-z0-9-]+-[0-9a-f]{12}\.svg$/,
      ),
    publicPath: z
      .string()
      .regex(/^\/wiki\/mm2r\/0\.99\/guides\/[a-z0-9-]+-[0-9a-f]{12}\.svg$/),
    width: z.number().int().positive(),
    height: z.number().int().positive(),
    contentHash: contentHashSchema,
    rightsStatus: z.literal('original_diagram'),
    license: z.literal('LicenseRef-Project-Original'),
    author: z.literal('Metal Max Wiki 项目原创'),
    captionZh: z.literal('原创流程示意 · 非实机地图 · 0.99未验证'),
    sourceRefs: z.array(guideSourceRefSchema).min(1),
  })
  .strict()
const guideSourceSchema = z
  .object({
    key: slugSchema,
    sourceId: slugSchema,
    title: z.string().min(1),
    url: z.url(),
    scope: z.enum(['mm2r-facts', 'rights-review']),
    encoding: z.enum(['auto', 'gb18030']),
    declaredLicense: z.enum(['NOASSERTION', 'CC-BY-NC-SA-4.0']),
    attribution: z.string().min(1),
    rightsScopeZh: z.string().min(1),
    retrievedAt: z.iso.datetime({ offset: true }),
    contentHash: contentHashSchema,
    licenseEvidenceText: z.string().nullable(),
    licenseUrl: z.url().nullable(),
    sourceRef: guideSourceRefSchema,
  })
  .strict()
const guideImageReferenceSchema = z
  .object({
    id: slugSchema,
    titleZh: z.string().min(1),
    sourcePageUrl: z.url(),
    sourceImageUrl: z.url(),
    rightsStatus: z.enum(['reference_only', 'rejected_wrong_version']),
    imageLicense: z.literal('NOASSERTION'),
    pageDeclaredLicense: z.string().min(1),
    localPath: z.null(),
    reasonZh: z.string().min(1),
    evidence: z.array(z.string()),
    sourceRef: guideSourceRefSchema,
  })
  .strict()
export const guideSummarySchema = z
  .object({
    slug: slugSchema,
    order: z.number().int().min(1).max(23),
    phaseId: guidePhaseIdSchema,
    title: z.string().min(1),
    location: z.string().min(1),
    kind: guideKindSchema,
    summary: z.string().min(1),
    stepCount: z.number().int().min(3),
    verificationStatus: verificationSchema,
  })
  .strict()
const guideRecordSchema = z
  .object({
    slug: slugSchema,
    order: z.number().int().min(1).max(23),
    phaseId: guidePhaseIdSchema,
    title: z.string().min(1),
    location: z.string().min(1),
    kind: guideKindSchema,
    summary: z.string().min(1),
    prerequisites: z.array(guideFactSchema).min(1),
    steps: z.array(guideFactSchema).min(3),
    keyItems: z.array(guideFactSchema),
    battles: z.array(guideBattleSchema),
    battleNote: z.string().min(1),
    cautions: z.array(guideFactSchema).min(1),
    nextSteps: z.array(guideFactSchema).min(1),
    nextChapterSlugs: z.array(slugSchema),
    sourceRefs: z.array(guideSourceRefSchema).min(1),
    verificationStatus: verificationSchema,
  })
  .strict()
const guideDatasetSchema = z
  .object({
    schemaVersion: z.literal(1),
    game: z.literal('mm2r'),
    targetVersion: z.literal('0.99'),
    versionScope: z.literal('mm2r-jp-reference'),
    verificationStatus: verificationSchema,
    title: z.string().min(1),
    referenceNote: z.string().min(1),
    routeNote: z.string().min(1),
    sourceLocatorNote: z.string().min(1),
    namesHash: contentHashSchema,
    snapshotHash: contentHashSchema,
    phases: z.array(guidePhaseSchema).length(6),
    records: z.array(guideRecordSchema).length(23),
    diagrams: z.array(guideDiagramSchema).length(3),
    imageReferences: z.array(guideImageReferenceSchema).min(2),
    sources: z.array(guideSourceSchema).min(1),
    limitations: z.array(z.string().min(1)).min(1),
  })
  .strict()
export const guideListDataSchema = z
  .object({
    title: z.string().min(1),
    referenceNote: z.string().min(1),
    routeNote: z.string().min(1),
    phases: z.array(guidePhaseSchema).length(6),
    list: z.array(guideSummarySchema),
    total: z.number().int().nonnegative(),
    chapterCount: z.number().int().positive(),
    diagrams: z.array(guideDiagramSchema),
    imageReferences: z.array(guideImageReferenceSchema),
    limitations: z.array(z.string().min(1)),
  })
  .strict()
export const guideDetailSchema = guideRecordSchema.extend({
  referenceNote: z.string().min(1),
  routeNote: z.string().min(1),
  phase: guidePhaseSchema,
  phases: z.array(guidePhaseSchema).length(6),
  chapters: z.array(guideSummarySchema).length(23),
  nextChapters: z.array(guideSummarySchema),
  diagrams: z.array(guideDiagramSchema),
  sources: z.array(guideSourceSchema).min(1),
  limitations: z.array(z.string().min(1)),
})

export type GuideFact = z.infer<typeof guideFactSchema>
export type GuideBattle = z.infer<typeof guideBattleSchema>
export type GuideDiagram = z.infer<typeof guideDiagramSchema>
export type GuidePhase = z.infer<typeof guidePhaseSchema>
export type GuideSummary = z.infer<typeof guideSummarySchema>
export type GuideDetail = z.infer<typeof guideDetailSchema>
export type GuideListData = z.infer<typeof guideListDataSchema>

export const guideKindLabels = {
  main: '主线必需',
  preparation: '推进前准备',
  optional: '可选支线',
} as const

/** 将快照字段转换为接口命名，保留来源原值字典的原始键名。 */
function toApiKeys(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(toApiKeys)
  if (typeof value !== 'object' || value === null) return value
  return Object.fromEntries(
    Object.entries(value).map(([key, item]) => [
      key.replace(/_([a-z0-9])/g, (_, letter: string) => letter.toUpperCase()),
      key === 'raw_values' ? item : toApiKeys(item),
    ]),
  )
}

const guideDataset = guideDatasetSchema.parse(toApiKeys(rawGuideDataset))
if (
  guideDataset.records.length !== guideSlugs.size ||
  guideDataset.records.some((record) => !guideSlugs.has(record.slug))
) {
  throw new Error('攻略路径索引与章节资料不一致，请重建资料')
}
export const guides: readonly HomeGuideSummary[] = guideDataset.records.map(
  (record) => ({
    slug: record.slug,
    title: record.title,
    summary: record.summary,
    sectionCount: 6,
    status: 'published',
  }),
)

/** 将编辑说明中的资料状态转换为读者可理解的中文。 */
export function guideReaderNote(value: string): string {
  return value
    .replaceAll('source_only', '仅核对公开来源')
    .replaceAll('cautions', '注意事项')
}

/** 服务端按阶段与关键词读取已校验的攻略摘要。 */
export async function getGuides(
  version: GameVersionSlug,
  query: { q?: string; phase?: string } = {},
): Promise<GuideListData> {
  const params = new URLSearchParams()
  if (query.q) params.set('q', query.q)
  if (query.phase) params.set('phase', query.phase)
  const suffix = params.size > 0 ? `?${params}` : ''
  return serverRequest(
    `/versions/${version}/guides${suffix}`,
    guideListDataSchema,
  )
}

/** 同一服务端请求内复用章节正文，保留真实的接口失败状态。 */
export const getGuide = cache(
  async (version: GameVersionSlug, slug: string): Promise<GuideDetail> =>
    serverRequest(
      `/versions/${version}/guides/${encodeURIComponent(slug)}`,
      guideDetailSchema,
    ),
)
