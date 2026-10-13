import type { Metadata } from 'next'

import { NotFoundContent } from '@/components/layout/NotFoundContent'

export const metadata: Metadata = {
  title: '资料不存在',
  robots: {
    index: false,
    follow: false,
  },
}

export default function NotFoundPage() {
  return <NotFoundContent />
}
