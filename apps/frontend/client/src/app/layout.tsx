import type { Metadata } from 'next'
import type { ReactNode } from 'react'

import { Geist } from 'next/font/google'

import { cn } from '@/lib/utils'

import './globals.css'

const geist = Geist({ subsets: ['latin'], variable: '--font-sans' })

export const metadata: Metadata = {
  title: {
    default: 'Metal Max Wiki',
    template: '%s | Metal Max Wiki',
  },
  description: '重装机兵资料百科与 AI 问答',
}

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="zh-CN" className={cn('font-sans', geist.variable)}>
      <body>{children}</body>
    </html>
  )
}
