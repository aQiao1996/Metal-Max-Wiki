import type { WikiAttribute } from '@/types/wiki'

interface AttributeTableProps {
  attributes: readonly WikiAttribute[]
}

export function AttributeTable({ attributes }: AttributeTableProps) {
  return (
    <section aria-labelledby="attributes-heading">
      <h2
        id="attributes-heading"
        className="text-xl font-semibold tracking-tight text-[var(--mm-navy)]"
      >
        基础资料
      </h2>
      <dl className="border-border mt-5 border-t">
        {attributes.map((attribute) => (
          <div
            key={attribute.label}
            className="border-border grid gap-1 border-b py-3.5 sm:grid-cols-[10rem_1fr] sm:gap-5"
          >
            <dt className="text-muted-foreground text-sm">{attribute.label}</dt>
            <dd className="text-foreground min-w-0 text-sm font-medium break-words">
              {attribute.value}
              {attribute.note && (
                <span className="text-muted-foreground mt-1 block font-normal">
                  {attribute.note}
                </span>
              )}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  )
}
