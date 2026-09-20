export default function HomePage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-zinc-950 px-6 text-zinc-50">
      <section className="max-w-xl text-center">
        <p className="mb-3 text-sm font-medium tracking-[0.3em] text-amber-400">
          METAL MAX WIKI
        </p>
        <h1 className="text-4xl font-semibold tracking-tight">
          基础框架已启动
        </h1>
        <p className="mt-4 text-base leading-7 text-zinc-400">
          用户端使用 Next.js、React、Tailwind CSS 和 shadcn/ui 构建。
        </p>
      </section>
    </main>
  )
}
