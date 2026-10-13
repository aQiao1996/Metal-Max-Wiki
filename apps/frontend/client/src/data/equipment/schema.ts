import { z } from 'zod'

const nonEmptyStringSchema = z.string().min(1)
const sourceHashSchema = z.string().regex(/^sha256:[0-9a-f]{64}$/)
const equipmentIdSchema = z.string().regex(/^[a-z0-9-]+-[0-9a-f]{10}$/)
const interimVerificationStatusSchema = z
  .enum(['compatible_candidate', 'verified_0_99'])
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

export const rawEquipmentRecordSchema = z
  .object({
    id: equipmentIdSchema,
    game: z.literal('mm2r'),
    target_version: z.literal('0.99'),
    domain: z.literal('equipment'),
    kind: z.enum(['human_weapon', 'main_cannon']),
    names: equipmentNamesSchema,
    attributes: z.record(z.string(), z.union([z.string(), z.number()])),
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
