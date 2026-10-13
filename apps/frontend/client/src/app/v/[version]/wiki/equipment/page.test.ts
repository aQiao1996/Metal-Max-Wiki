import { isValidElement, type ReactElement, type ReactNode } from 'react'
import { describe, expect, it } from 'vitest'

import { EquipmentFilterForm } from '@/components/equipment/EquipmentFilterForm'

import EquipmentPage from './page'

function findElement(
  node: ReactNode,
  type: ReactElement['type'],
): ReactElement | undefined {
  if (!isValidElement(node)) {
    return undefined
  }

  if (node.type === type) {
    return node
  }

  const children = (node.props as { children?: ReactNode }).children

  if (Array.isArray(children)) {
    for (const child of children) {
      const match = findElement(child, type)

      if (match !== undefined) {
        return match
      }
    }

    return undefined
  }

  return findElement(children, type)
}

async function renderFilterForm(searchParams: Record<string, string>) {
  const page = await EquipmentPage({
    params: Promise.resolve({ version: 'mm2r-099' }),
    searchParams: Promise.resolve(searchParams),
  })
  const form = findElement(page, EquipmentFilterForm)

  if (form === undefined) {
    throw new Error('装备页缺少筛选表单')
  }

  return form
}

describe('EquipmentPage', () => {
  it('查询条件变化时重建未受控筛选表单', async () => {
    const mainCannonForm = await renderFilterForm({
      type: 'main-cannon',
      sort: 'attack-desc',
    })
    const humanWeaponForm = await renderFilterForm({
      type: 'human-weapon',
    })

    expect(mainCannonForm.key).not.toBe(humanWeaponForm.key)
  })
})
