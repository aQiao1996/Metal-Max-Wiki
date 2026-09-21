import { redirect } from 'next/navigation'

import { defaultGameVersion } from '@/config/game-versions'

export default function HomePage() {
  redirect(`/v/${defaultGameVersion}`)
}
