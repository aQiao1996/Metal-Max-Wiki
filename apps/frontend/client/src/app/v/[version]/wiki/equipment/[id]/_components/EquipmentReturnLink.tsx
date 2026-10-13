'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'

import { ArrowLeft } from 'lucide-react'

import { buildEquipmentReturnHref } from '../_lib/equipment-detail'

interface EquipmentReturnLinkProps {
  version: string
  variant: 'breadcrumb' | 'footer'
}

export function EquipmentReturnLink({
  version,
  variant,
}: EquipmentReturnLinkProps) {
  const from = useSearchParams().get('from') ?? undefined
  const href = buildEquipmentReturnHref(version, from)

  if (variant === 'breadcrumb') {
    return (
      <Link
        href={href}
        className="hover:text-foreground focus-visible:ring-ring inline-flex min-h-10 items-center focus-visible:ring-2 focus-visible:outline-none"
      >
        装备百科
      </Link>
    )
  }

  return (
    <Link
      href={href}
      className="focus-visible:ring-ring mt-10 inline-flex min-h-10 items-center gap-2 text-sm font-medium text-[var(--mm-navy)] underline-offset-4 hover:underline focus-visible:ring-2 focus-visible:outline-none"
    >
      <ArrowLeft className="size-4" aria-hidden="true" />
      返回装备列表
    </Link>
  )
}
