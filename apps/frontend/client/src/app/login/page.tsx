import type { Metadata } from 'next'
import Link from 'next/link'

import { ArrowLeft } from 'lucide-react'

import { defaultGameVersion } from '@/config/game-versions'
import { buildVersionPath } from '@/lib/version-routes'
import { LoginForm } from '@/components/auth/LoginForm'

export const metadata: Metadata = {
  title: '登录',
}

export default function LoginPage() {
  return (
    <main className="grid min-h-screen lg:grid-cols-[minmax(20rem,0.8fr)_minmax(32rem,1.2fr)]">
      <section className="hidden flex-col justify-between bg-[var(--mm-navy)] p-10 text-white lg:flex xl:p-14">
        <Link
          href={buildVersionPath(defaultGameVersion)}
          className="focus-visible:ring-sidebar-ring inline-flex w-fit items-center gap-2 text-sm text-white/65 hover:text-white focus-visible:ring-2 focus-visible:outline-none"
        >
          <ArrowLeft className="size-4" />
          返回资料库
        </Link>
        <div className="max-w-md">
          <p className="text-xs font-semibold tracking-[0.2em] text-[#ff9a76] uppercase">
            Metal Max Archive
          </p>
          <h1 className="mt-5 text-4xl font-semibold tracking-tight xl:text-5xl">
            让每条结论都能找到版本和来源。
          </h1>
          <p className="mt-5 text-base leading-7 text-white/62">
            百科可以直接浏览，登录只用于 AI 问答与后续的个人功能。
          </p>
        </div>
        <p className="text-xs text-white/35">yangyunqiao.top</p>
      </section>

      <section className="flex min-h-screen items-center justify-center px-5 py-12 sm:px-8">
        <div className="w-full max-w-sm">
          <Link
            href={buildVersionPath(defaultGameVersion)}
            className="text-muted-foreground hover:text-foreground focus-visible:ring-ring mb-10 inline-flex min-h-10 items-center gap-2 text-sm focus-visible:ring-2 focus-visible:outline-none lg:hidden"
          >
            <ArrowLeft className="size-4" />
            返回资料库
          </Link>
          <p className="text-xs font-semibold tracking-[0.16em] text-[var(--mm-signal)] uppercase">
            Account
          </p>
          <h2 className="mt-3 text-3xl font-semibold tracking-tight text-[var(--mm-navy)]">
            登录账号
          </h2>
          <p className="text-muted-foreground mt-2 text-sm leading-6">
            使用邮箱和密码登录。
          </p>
          <div className="mt-8">
            <LoginForm />
          </div>
        </div>
      </section>
    </main>
  )
}
