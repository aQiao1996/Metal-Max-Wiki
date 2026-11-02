'use client'

import Link from 'next/link'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { currentUserKey, logout } from '@/api/auth'
import { useCurrentUser } from '@/hooks/useCurrentUser'
import { Button } from '@/components/ui/button'

export function AccountMenu() {
  const user = useCurrentUser()
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: logout,
    onSuccess: () => {
      client.setQueryData(currentUserKey, null)
    },
  })
  if (user.isPending)
    return <span className="text-muted-foreground text-xs">正在读取账号…</span>
  if (user.isError)
    return (
      <button
        type="button"
        onClick={() => user.refetch()}
        className="text-destructive text-xs"
      >
        账号读取失败，重试
      </button>
    )
  if (!user.data)
    return (
      <Button asChild variant="outline">
        <Link href="/login">登录 / 注册</Link>
      </Button>
    )
  return (
    <div className="flex min-w-0 items-center gap-2">
      <span
        className="text-muted-foreground max-w-36 truncate text-xs"
        title={user.data.email}
      >
        {user.data.email}
      </span>
      <Button
        variant="ghost"
        onClick={() => mutation.mutate()}
        disabled={mutation.isPending}
      >
        退出
      </Button>
      {mutation.isError && (
        <span role="alert" className="text-destructive text-xs">
          退出失败，请重试
        </span>
      )}
    </div>
  )
}
