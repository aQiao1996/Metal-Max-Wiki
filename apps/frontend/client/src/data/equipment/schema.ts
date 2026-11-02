import { z } from 'zod'

const nonEmptyStringSchema = z.string().min(1)
const sourceHashSchema = z.string().regex(/^sha256:[0-9a-f]{64}$/)
const equipmentIdSchema = z.string().regex(/^[a-z0-9-]+-[0-9a-f]{10}$/)
const interimVerificationStatusSchema = z
  .enum(['source_only', 'compatible_candidate', 'verified_0_99'])
  .superRefine((status, context) => {
    if (status === 'verified_0_99') {
      context.addIssue({
        code: 'custom',
        message: '中间记录不能标记为 verified_0_99',
      })
    }
  })
const sourceUrlSchema = z.url().refine(
  (value) => {
    try {
      const protocol = new URL(value).protocol
      return protocol === 'http:' || protocol === 'https:'
    } catch {
      return false
    }
  },
  { message: '来源地址仅支持 HTTP(S) 协议' },
)

const equipmentNamesSchema = z
  .object({
    ja: nonEmptyStringSchema.nullable(),
    zh_09: nonEmptyStringSchema.nullable(),
    zh_099: nonEmptyStringSchema.nullable(),
    zh_reference: nonEmptyStringSchema.nullable().optional(),
    aliases: z.array(nonEmptyStringSchema),
  })
  .strict()

const equipmentSourceRefSchema = z
  .object({
    source_id: nonEmptyStringSchema,
    target_id: nonEmptyStringSchema,
    source_url: sourceUrlSchema,
    retrieved_at: z.iso.datetime({ offset: true }),
    content_hash: sourceHashSchema,
    table_index: z.number().int().nonnegative(),
    row_index: z.number().int().nonnegative(),
  })
  .strict()

const equipmentSourceSpanSchema = z
  .object({
    source_id: nonEmptyStringSchema,
    target_id: nonEmptyStringSchema,
    table_index: z.number().int().nonnegative(),
    row_index: z.number().int().nonnegative(),
    start_header: nonEmptyStringSchema,
    end_header: nonEmptyStringSchema,
    value: nonEmptyStringSchema,
  })
  .strict()

const modificationSchema = z
  .object({
    stars: z.number().int().min(0).max(3),
    attack_min_raw: z.string(),
    attack_raw: z.string(),
    attack_max_raw: z.string(),
    defense_min_raw: z.string(),
    defense_raw: z.string(),
    defense_max_raw: z.string(),
    magazine_min_raw: z.string(),
    magazine_raw: z.string(),
    magazine_max_raw: z.string(),
    weight_min_raw: z.string(),
    weight_raw: z.string(),
    weight_max_raw: z.string(),
  })
  .strict()

const controlModificationSchema = modificationSchema
  .omit({
    attack_min_raw: true,
    attack_raw: true,
    attack_max_raw: true,
    magazine_min_raw: true,
    magazine_raw: true,
    magazine_max_raw: true,
  })
  .extend({
    accuracy_min_raw: z.string(),
    accuracy_raw: z.string(),
    accuracy_max_raw: z.string(),
    evasion_min_raw: z.string(),
    evasion_raw: z.string(),
    evasion_max_raw: z.string(),
  })

const engineModificationSchema = controlModificationSchema
  .omit({
    accuracy_min_raw: true,
    accuracy_raw: true,
    accuracy_max_raw: true,
    evasion_min_raw: true,
    evasion_raw: true,
    evasion_max_raw: true,
  })
  .extend({ capacity_raw: z.string() })

export const rawEquipmentRecordSchema = z
  .object({
    id: equipmentIdSchema,
    game: z.literal('mm2r'),
    target_version: z.literal('0.99'),
    domain: z.literal('equipment'),
    kind: z.enum([
      'human_weapon',
      'main_cannon',
      'special_equipment',
      'c_unit',
      'engine',
    ]),
    names: equipmentNamesSchema,
    attributes: z.record(z.string(), z.union([z.string(), z.number()])),
    modifications: z.array(modificationSchema).optional(),
    control_modifications: z.array(controlModificationSchema).optional(),
    engine_modifications: z.array(engineModificationSchema).optional(),
    version_scope: z.array(nonEmptyStringSchema),
    verification_status: interimVerificationStatusSchema,
    source_refs: z.array(equipmentSourceRefSchema).min(1),
    source_spans: z.array(equipmentSourceSpanSchema),
    issues: z.array(nonEmptyStringSchema),
    asset_refs: z.array(nonEmptyStringSchema),
  })
  .strict()

export const equipmentDatasetSchema = z
  .object({
    schema_version: z.literal(1),
    game: z.literal('mm2r'),
    target_version: z.literal('0.99'),
    domain: z.literal('equipment'),
    source_hashes: z.array(sourceHashSchema),
    records: z.array(rawEquipmentRecordSchema),
  })
  .strict()

export type RawEquipmentRecord = z.infer<typeof rawEquipmentRecordSchema>
export type EquipmentDataset = z.infer<typeof equipmentDatasetSchema>
