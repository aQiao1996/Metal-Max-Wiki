import type { ReferenceTable } from '@/data/knowledge/schema'

interface ReferenceDataTableProps {
  table: ReferenceTable
}

/** 宽表在自身区域滚动，保留原始行条件与空缺。 */
export function ReferenceDataTable({ table }: ReferenceDataTableProps) {
  return (
    <div className="min-w-0">
      <div
        className="border-border max-w-full overflow-x-auto rounded border"
        role="region"
        aria-label={table.caption}
        tabIndex={0}
      >
        <table className="w-full border-collapse text-left text-sm">
          <caption className="border-border text-muted-foreground border-b px-3 py-3 text-left text-xs">
            {table.caption}
          </caption>
          <thead className="bg-muted">
            <tr>
              {table.headers.map((header, index) => (
                <th
                  key={index}
                  scope="col"
                  className="border-border border-b px-3 py-2 font-medium whitespace-nowrap text-[var(--mm-navy)]"
                >
                  {header || '条件'}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr
                key={rowIndex}
                className="border-border border-b last:border-b-0"
              >
                {row.map((cell, index) => (
                  <td
                    key={index}
                    className="max-w-80 min-w-20 px-3 py-2 align-top break-words"
                  >
                    {cell && cell !== 't' && cell !== '?t' ? cell : '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
