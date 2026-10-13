import { BadgeCheck, CircleDashed } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import type { EquipmentEntry } from '@/types/equipment'

interface EquipmentVerificationBadgeProps {
  status: EquipmentEntry['verification_status']
}

export function EquipmentVerificationBadge({
  status,
}: EquipmentVerificationBadgeProps) {
  if (status === 'verified_0_99') {
    return (
      <Badge
        variant="secondary"
        className="text-foreground rounded font-normal"
      >
        <BadgeCheck aria-hidden="true" />
        0.99 已验证
      </Badge>
    )
  }

  return (
    <Badge
      variant="outline"
      className="bg-accent text-accent-foreground rounded font-normal"
    >
      <CircleDashed aria-hidden="true" />
      兼容候选
    </Badge>
  )
}
