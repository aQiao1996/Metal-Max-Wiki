import { createHash } from 'node:crypto'
import { z } from 'zod'

import proofs from '../../../../../../data/processed/mm2r/0.99/equipment-names.json'
import {
  romNameProofSchema,
  type EquipmentRecord,
  type RawEquipmentRecord,
} from './schema'

const hashSchema = z.string().regex(/^sha256:[0-9a-f]{64}$/)
const datasetSchema = z
  .object({
    schema_version: z.literal(1),
    verification_status: z.literal('verified_0_99'),
    scope: z.literal('equipment_names_only'),
    equipment_hash: hashSchema,
    identity_catalog_hash: hashSchema,
    rom: z
      .object({
        schema_version: z.literal(1),
        title: z.literal('METALMAX2R'),
        game_code: z.literal('TMXJ'),
        user_version: z.literal('0.99'),
        size: z.number().int().min(512).max(268435456),
        sha256: hashSchema,
        version_basis: z.string().min(1),
      })
      .strict(),
    records: z.array(romNameProofSchema).min(1),
  })
  .strict()

function ordered(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(ordered)
  if (value !== null && typeof value === 'object')
    return Object.fromEntries(
      Object.entries(value)
        .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
        .map(([key, item]) => [key, ordered(item)]),
    )
  return value
}

function nameKey(value: string) {
  return value.normalize('NFKC').toLowerCase().replaceAll(' ', '')
}

function referenceParameters(
  record: RawEquipmentRecord,
): Record<string, string> | undefined {
  const fields =
    record.kind === 'engine'
      ? ['weight_raw', 'defense_raw', 'capacity_raw']
      : record.kind === 'c_unit'
        ? ['weight_raw', 'defense_raw', 'accuracy_raw', 'evasion_raw']
        : ['weight_raw', 'defense_raw', 'attack_raw', 'magazine_raw']
  const modifications =
    record.kind === 'engine'
      ? record.engine_modifications
      : record.kind === 'c_unit'
        ? record.control_modifications
        : record.modifications
  const zero = modifications?.find((mod) => mod.stars === 0)
  if (
    !zero &&
    record.attributes.stat_condition_raw &&
    !String(record.attributes.stat_condition_raw).startsWith('0 ')
  )
    return undefined
  const values: Record<string, unknown> = zero ?? record.attributes
  const result: Record<string, string> = {}
  for (const field of fields) {
    let raw = String(values[field] ?? '')
      .replace(/t$/, '')
      .trim()
    if (field === 'magazine_raw' && raw === '∞') raw = '0'
    if (!/^[0-9]+(?:\.[0-9]+)?$/.test(raw)) return undefined
    result[field] = String(Number(raw))
  }
  return result
}

/** 只覆盖已核对的名称字段，保留数值与机制的原参考状态。 */
export function applyVerifiedNames(
  records: readonly RawEquipmentRecord[],
): EquipmentRecord[] {
  const dataset = datasetSchema.parse(proofs)
  const registry = [...records]
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((record) => ({
      id: record.id,
      kind: record.kind,
      names: {
        ...record.names,
        zh_reference: record.names.zh_reference ?? null,
      },
    }))
  const hash = `sha256:${createHash('sha256')
    .update(JSON.stringify(ordered(registry)))
    .digest('hex')}`
  if (dataset.equipment_hash !== hash)
    throw new Error('ROM 名称证据与装备名称目录不一致')
  const identities = [...records]
    .sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0))
    .map((record) => ({
      id: record.id,
      kind: record.kind,
      parameters:
        record.kind !== 'human_weapon'
          ? (referenceParameters(record) ?? null)
          : null,
      price: String(record.attributes.price_raw ?? ''),
    }))
  const identityHash = `sha256:${createHash('sha256')
    .update(JSON.stringify(ordered(identities)))
    .digest('hex')}`
  if (dataset.identity_catalog_hash !== identityHash)
    throw new Error('ROM 名称关联的参数匹配目录已变化')
  const kinds: Record<RawEquipmentRecord['kind'], number> = {
    human_weapon: 1,
    engine: 12,
    c_unit: 13,
    main_cannon: 14,
    sub_gun: 15,
    special_equipment: 16,
  }
  const byId = new Map(dataset.records.map((proof) => [proof.id, proof]))
  const itemIds = new Set(dataset.records.map((proof) => proof.item_id))
  const ids = new Set(records.map((record) => record.id))
  if (
    byId.size !== dataset.records.length ||
    itemIds.size !== dataset.records.length ||
    [...byId.keys()].some((id) => !ids.has(id))
  )
    throw new Error('ROM 名称证据存在重复或未知条目')
  return records.map((record) => {
    const proof = byId.get(record.id)
    if (!proof) return record
    const aliases = [
      record.names.ja,
      record.names.zh_09,
      record.names.zh_099,
      record.names.zh_reference,
      ...record.names.aliases,
    ]
    if (
      proof.item_kind !== kinds[record.kind] ||
      !aliases.includes(proof.matched_alias) ||
      Buffer.byteLength(proof.value, 'utf16le') !== proof.name_bytes ||
      proof.record_offset + 12 > dataset.rom.size ||
      proof.name_offset + proof.name_bytes + 2 > dataset.rom.size
    )
      throw new Error(`ROM 名称证据与条目不符：${record.id}`)
    if (proof.method === 'rom_extraction_exact_name') {
      if (
        proof.identity_parameters !== undefined ||
        proof.identity_price !== undefined ||
        proof.identity_review !== undefined ||
        nameKey(proof.value) !== nameKey(proof.matched_alias)
      )
        throw new Error(`ROM 同名核验证据不符：${record.id}`)
    } else if (proof.method === 'rom_extraction_reviewed_identity') {
      const review = proof.identity_review
      const rawAttributes = Object.fromEntries(
        Object.entries(record.attributes).filter(([key]) =>
          key.endsWith('_raw'),
        ),
      )
      const sourceHashes = [
        ...new Set(record.source_refs.map((ref) => ref.content_hash)),
      ].sort()
      if (
        !review ||
        proof.identity_parameters !== undefined ||
        proof.identity_price !== undefined ||
        review.id !== proof.id ||
        review.item_id !== proof.item_id ||
        review.value !== proof.value ||
        review.matched_alias !== proof.matched_alias ||
        JSON.stringify(ordered(rawAttributes)) !==
          JSON.stringify(ordered(review.reference_attributes)) ||
        JSON.stringify(sourceHashes) !==
          JSON.stringify(review.reference_source_hashes)
      )
        throw new Error(`ROM 人工身份的来源依据已变化：${record.id}`)
    } else {
      const expected = referenceParameters(record)
      if (
        !expected ||
        !proof.identity_parameters ||
        proof.identity_review !== undefined ||
        Object.keys(proof.identity_parameters).length < 3 ||
        JSON.stringify(ordered(expected)) !==
          JSON.stringify(ordered(proof.identity_parameters)) ||
        (proof.identity_price !== undefined &&
          String(proof.identity_price) !==
            String(record.attributes.price_raw ?? '').replace(/^\*/, ''))
      )
        throw new Error(`ROM 名称参数关联已变化：${record.id}`)
    }
    const oldName = record.names.zh_099
    const preserved = [...record.names.aliases]
    if (oldName && oldName !== proof.value && !preserved.includes(oldName))
      preserved.push(oldName)
    return {
      ...record,
      names: { ...record.names, zh_099: proof.value, aliases: preserved },
      name_verification: { ...proof, rom_sha256: dataset.rom.sha256 },
    }
  })
}
