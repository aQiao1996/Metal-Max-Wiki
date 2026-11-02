import { Search } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface SearchFieldProps {
  defaultValue?: string
}

export function SearchField({ defaultValue = '' }: SearchFieldProps) {
  return (
    <form role="search" className="flex max-w-3xl gap-2">
      <label className="relative min-w-0 flex-1">
        <span className="sr-only">搜索资料</span>
        <Search className="text-muted-foreground absolute top-1/2 left-3 size-4 -translate-y-1/2" />
        <Input
          name="q"
          maxLength={100}
          defaultValue={defaultValue}
          placeholder="输入正式名称、简称或关键词"
          className="bg-card h-11 pl-9"
        />
      </label>
      <Button type="submit" size="lg" className="h-11 px-5">
        搜索
      </Button>
    </form>
  )
}
