'use client'

import { Button } from '@/components/ui/button'

export default function VersionError({ reset }: { reset: () => void }) {
  return (
    <section className="mx-auto max-w-xl py-16">
      <h1 className="text-2xl font-semibold text-[var(--mm-navy)]">
        暂时无法读取资料
      </h1>
      <p role="alert" className="text-muted-foreground mt-4 text-sm leading-7">
        请稍后重试。如果你正在本地开发，请确认后端服务已经启动。
      </p>
      <Button onClick={reset} className="mt-6">
        重新加载
      </Button>
    </section>
  )
}
