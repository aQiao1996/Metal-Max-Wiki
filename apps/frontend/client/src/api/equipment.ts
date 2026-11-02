import { z } from 'zod'

import { equipmentRecordSchema } from '@/data/equipment/schema'
import { toEquipmentEntry } from '@/data/equipment/entry'
import { restoreSourceKeys } from '@/lib/request/source-keys'
import { equipmentTypeIds } from '@/types/equipment'

const apiRecordSchema = z
  .preprocess(restoreSourceKeys, equipmentRecordSchema)
  .transform(toEquipmentEntry)
export const equipmentPageSchema = z.object({
  list: z.array(apiRecordSchema),
  typeCounts: z.record(
    z.enum(equipmentTypeIds),
    z.number().int().nonnegative(),
  ),
  elements: z.array(z.string()),
  traits: z.array(z.string()),
  pagination: z.object({
    page: z.number().int().positive(),
    pageSize: z.number().int().positive(),
    total: z.number().int().nonnegative(),
    totalPages: z.number().int().nonnegative(),
    hasNext: z.boolean(),
    hasPrev: z.boolean(),
  }),
})
