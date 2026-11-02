import { z } from 'zod'

const sourcePath = z
  .string()
  .regex(/^data\/raw\/mm2r\/0\.99\/[a-z0-9/-]+\.json$/)
const sourceHash = z.string().regex(/^sha256:[0-9a-f]{64}$/)
const jsonPointer = z.string().regex(/^#\/.+/)

const referenceParameter = z
  .object({
    field: z.enum([
      'attack_raw',
      'defense_raw',
      'weight_raw',
      'capacity_raw',
      'magazine_raw',
      'accuracy_raw',
      'evasion_raw',
    ]),
    source_path: sourcePath,
    source_sha256: sourceHash,
    json_pointer: jsonPointer,
    raw_value: z.string().regex(/^[0-9]+(?:\.[0-9]+)?t?$/),
  })
  .strict()

export const identityReviewSchema = z
  .object({
    id: z.string().regex(/^[a-z0-9-]+-[0-9a-f]{10}$/),
    item_id: z.number().int().nonnegative(),
    value: z.string().min(1).max(128),
    matched_alias: z.string().min(1),
    reference_attributes: z
      .record(z.string(), z.string())
      .refine((v) => Object.keys(v).length >= 2),
    reference_source_hashes: z.array(sourceHash).min(1),
    parameter_table: z.enum([
      'ENGINE.ARR',
      'CUNIT.ARR',
      'CARWEPON.ARR',
      'NINGEN_BUKI.ARR',
    ]),
    parameter_index: z.number().int().nonnegative(),
    parameter_hex: z.string().regex(/^(?:[0-9a-f]{2}){8,20}$/),
    base_parameters: z.array(referenceParameter),
    source_evidence: z.array(
      z
        .object({
          source_path: sourcePath,
          source_sha256: sourceHash,
          json_pointer: jsonPointer,
          value_json: z.string().min(1).max(50000),
          note_zh: z.string().min(1).max(1000),
        })
        .strict(),
    ),
    rom_evidence: z.array(
      z
        .object({
          archive: z.enum(['xls/data/pack_data.pak', 'xls/pack_data.pak']),
          file: z.string().regex(/^[A-Z0-9_]+\.(?:ARR|NAM|SET)$/),
          offset: z.number().int().nonnegative(),
          hex: z.string().regex(/^(?:[0-9a-f]{2}){1,512}$/),
          note_zh: z.string().min(1).max(1000),
        })
        .strict(),
    ),
    note_zh: z.string().min(10).max(2000),
  })
  .strict()
  .refine((review) => {
    const widths = {
      'ENGINE.ARR': 12,
      'CUNIT.ARR': 12,
      'CARWEPON.ARR': 20,
      'NINGEN_BUKI.ARR': 8,
    }
    return (
      review.parameter_hex.length === widths[review.parameter_table] * 2 &&
      new Set(review.base_parameters.map((p) => p.field)).size ===
        review.base_parameters.length
    )
  }, '人工身份记录宽度无效或基础字段重复')
