import { z } from 'zod'

import { equipmentPageSchema } from '@/api/equipment'
import { toKnowledgeEntry } from '@/data/knowledge/entry'
import {
  rawKnowledgeRecordSchema,
  rawKnowledgeSummarySchema,
} from '@/data/knowledge/schema'
import { restoreSourceKeys } from '@/lib/request/source-keys'

export const apiKnowledgeRecordSchema = z
  .preprocess(restoreSourceKeys, rawKnowledgeRecordSchema)
  .transform((record) => toKnowledgeEntry(record))
export const knowledgePageSchema = z
  .object({
    list: z.array(
      z
        .preprocess(restoreSourceKeys, rawKnowledgeSummarySchema)
        .transform((record) => toKnowledgeEntry(record)),
    ),
    pagination: equipmentPageSchema.shape.pagination,
  })
  .strict()
