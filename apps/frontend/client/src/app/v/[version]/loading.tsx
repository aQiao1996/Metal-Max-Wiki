import { Skeleton } from '@/components/ui/skeleton'

export default function VersionLoading() {
  return (
    <div className="space-y-12" aria-label="页面加载中" aria-busy="true">
      <section>
        <Skeleton className="h-4 w-28" />
        <Skeleton className="mt-4 h-11 w-56" />
        <Skeleton className="mt-4 h-5 w-full max-w-xl" />
        <div className="border-border mt-8 grid grid-cols-2 border-t border-l lg:grid-cols-4">
          {Array.from({ length: 8 }, (_, index) => (
            <div
              key={index}
              className="border-border bg-card h-40 border-r border-b p-5"
            >
              <Skeleton className="h-3 w-6" />
              <Skeleton className="mt-10 h-6 w-20" />
              <Skeleton className="mt-3 h-4 w-full" />
            </div>
          ))}
        </div>
      </section>
      <section className="grid gap-8 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="space-y-4">
          <Skeleton className="h-8 w-32" />
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-20 w-full" />
          ))}
        </div>
        <Skeleton className="h-96 w-full" />
      </section>
    </div>
  )
}
