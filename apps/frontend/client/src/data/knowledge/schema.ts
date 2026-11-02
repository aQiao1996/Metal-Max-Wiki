import { z } from 'zod'

import { rawEquipmentRecordSchema } from '@/data/equipment/schema'

export const knowledgeCategories = [
  'wanted-monsters',
  'vehicles',
  'jobs',
] as const
export const knowledgeCategorySchema = z.enum(knowledgeCategories)

const sourceRefsSchema = rawEquipmentRecordSchema.shape.source_refs
const attributeSchema = z
  .object({ label: z.string().min(1), value: z.string().min(1) })
  .strict()
const tableSchema = z
  .object({
    caption: z.string().min(1),
    headers: z.array(z.string()).min(1),
    rows: z.array(z.array(z.string())),
    source_refs: sourceRefsSchema,
  })
  .strict()
  .superRefine((table, context) => {
    if (table.rows.some((row) => row.length !== table.headers.length)) {
      context.addIssue({
        code: 'custom',
        message: `${table.caption}：表格行宽与表头不一致`,
      })
    }
  })
const sectionSchema = z
  .object({
    id: z.string().regex(/^[a-z0-9-]+$/),
    title: z.string().min(1),
    paragraphs: z.array(z.string().min(1)),
    tables: z.array(tableSchema),
    source_refs: sourceRefsSchema,
  })
  .strict()
const dropSchema = z
  .object({
    slot: z.number().int().min(1).max(3),
    item_ja: z.string().min(1),
    name: z.string().min(1),
    rate_raw: z.string().regex(/^(?:100|[1-9]?[0-9])%$/),
    summary: z.string(),
    equipment_id: rawEquipmentRecordSchema.shape.id.nullable(),
    attributes: z.array(attributeSchema),
    tables: z.array(tableSchema),
    source_refs: sourceRefsSchema,
    issues: z.array(z.string()),
  })
  .strict()
const enemySchema = z
  .object({
    name_ja: z.string().min(1),
    encyclopedia_number: z.string().regex(/^[0-9]{3}$/),
    drops: z.array(dropSchema).length(3),
  })
  .strict()
  .superRefine((enemy, context) => {
    if (enemy.drops.some((drop, index) => drop.slot !== index + 1)) {
      context.addIssue({
        code: 'custom',
        message: `${enemy.name_ja}：掉落槽顺序不完整`,
      })
    }
  })

const vehicleSetupSchema = z
  .object({
    id: rawEquipmentRecordSchema.shape.id,
    kind: z.enum(['pattern', 'preset', 'fixed']),
    stage: z.number().int().min(1).max(128),
    name_ja: z.string().min(1),
    name_reference: z.string().min(1),
    holes_raw: z.array(z.string().min(1)).length(5),
    weight_raw: z.string(),
    trait_ja: z.string().min(1),
    trait_name: z.string().min(1),
    cargo_raw: z.string(),
    fixed_armament_raw: z.string().nullable(),
    source_ref: rawEquipmentRecordSchema.shape.source_refs.element,
    issues: z.array(z.string()),
  })
  .strict()
const vehicleDetailsSchema = z
  .object({
    double_engine_supported: z.boolean(),
    double_c_unit_supported: z.boolean(),
    configurations: z.array(vehicleSetupSchema).min(1).max(128),
    design_traits_ja: z.array(z.string()),
    trait_terms: z.array(z.string().min(1)).min(1),
  })
  .strict()
  .superRefine((vehicle, context) => {
    if (
      new Set(vehicle.configurations.map(({ id }) => id)).size !==
      vehicle.configurations.length
    ) {
      context.addIssue({ code: 'custom', message: '战车配置包含重复ID' })
    }
  })

const knowledgeSummaryShape = {
  id: rawEquipmentRecordSchema.shape.id,
  game: z.literal('mm2r'),
  target_version: z.literal('0.99'),
  category: knowledgeCategorySchema,
  names: rawEquipmentRecordSchema.shape.names,
  bounty: z.number().int().nonnegative().nullable(),
  summary: z.string().min(1),
  tags: z.array(z.string()),
  verification_status: rawEquipmentRecordSchema.shape.verification_status,
}

export const rawKnowledgeSummarySchema = z
  .object(knowledgeSummaryShape)
  .strict()

export const rawKnowledgeRecordSchema = z
  .object({
    ...knowledgeSummaryShape,
    attributes: z.array(attributeSchema),
    sections: z.array(sectionSchema),
    enemies: z.array(enemySchema),
    probability_note: z.string(),
    vehicle: vehicleDetailsSchema.optional(),
    version_scope: z.array(z.string().min(1)).min(1),
    source_refs: sourceRefsSchema,
    issues: z.array(z.string()),
  })
  .strict()
  .superRefine((record, context) => {
    if (record.category === 'wanted-monsters' && record.bounty === null) {
      context.addIssue({
        code: 'custom',
        message: `${record.id}：赏金首缺少赏金`,
      })
    }
    if (record.category === 'vehicles' && record.vehicle === undefined) {
      context.addIssue({
        code: 'custom',
        message: `${record.id}：战车缺少配置信息`,
      })
    }
    if (
      new Set(record.sections.map(({ id }) => id)).size !==
      record.sections.length
    ) {
      context.addIssue({
        code: 'custom',
        message: `${record.id}：正文存在重复定位`,
      })
    }
  })

export const knowledgeDatasetSchema = z
  .object({
    schema_version: z.literal(1),
    game: z.literal('mm2r'),
    target_version: z.literal('0.99'),
    category: knowledgeCategorySchema,
    records: z.array(rawKnowledgeRecordSchema),
  })
  .strict()
  .superRefine((dataset, context) => {
    if (
      new Set(dataset.records.map(({ id }) => id)).size !==
      dataset.records.length
    ) {
      context.addIssue({ code: 'custom', message: '百科数据包含重复ID' })
    }
    if (
      dataset.records.some((record) => record.category !== dataset.category)
    ) {
      context.addIssue({
        code: 'custom',
        message: '百科条目与数据集分类不一致',
      })
    }
  })

export type KnowledgeCategory = z.infer<typeof knowledgeCategorySchema>
export type RawKnowledgeRecord = z.infer<typeof rawKnowledgeRecordSchema>
export type RawKnowledgeSummary = z.infer<typeof rawKnowledgeSummarySchema>
export type ReferenceTable = z.infer<typeof tableSchema>
export type WantedEnemy = z.infer<typeof enemySchema>
export type VehicleDetails = z.infer<typeof vehicleDetailsSchema>
