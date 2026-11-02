'use client'

import { type FormEvent, useState } from 'react'
import { useRouter } from 'next/navigation'
import { useMutation, useQueryClient } from '@tanstack/react-query'

import { Eye, EyeOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { authenticate, currentUserKey } from '@/api/auth'

interface FormErrors {
  email?: string
  password?: string
  form?: string
}

export function LoginForm({
  nextPath = '/v/mm2r-099/ai',
}: {
  nextPath?: string
}) {
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<FormErrors>({})
  const router = useRouter()
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: ({ email, password }: { email: string; password: string }) =>
      authenticate(mode, email, password),
    onSuccess: (user) => {
      client.setQueryData(currentUserKey, user)
      router.replace(nextPath)
      router.refresh()
    },
  })

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const formData = new FormData(event.currentTarget)
    const email = String(formData.get('email') ?? '').trim()
    const password = String(formData.get('password') ?? '')
    const nextErrors: FormErrors = {}

    if (!email) {
      nextErrors.email = '请输入邮箱。'
    } else if (!/^\S+@\S+\.\S+$/.test(email)) {
      nextErrors.email = '邮箱格式不正确。'
    }

    if (!password) {
      nextErrors.password = '请输入密码。'
    } else if (
      password.length > 128 ||
      (mode === 'register' && password.length < 15)
    ) {
      nextErrors.password =
        '注册密码需要 15–128 个字符，可以使用一句容易记住的话。'
    } else if (
      mode === 'register' &&
      password !== formData.get('confirmPassword')
    ) {
      nextErrors.password = '两次输入的密码不一致。'
    }

    if (Object.keys(nextErrors).length === 0) {
      mutation.mutate({ email, password })
    }

    setErrors(nextErrors)
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-5">
      <div
        className="border-border flex border-b"
        role="group"
        aria-label="账号操作"
      >
        {(['login', 'register'] as const).map((item) => (
          <button
            key={item}
            type="button"
            disabled={mutation.isPending}
            aria-pressed={mode === item}
            onClick={() => {
              setMode(item)
              setErrors({})
              mutation.reset()
            }}
            className={`min-h-11 flex-1 border-b-2 text-sm font-medium ${mode === item ? 'border-[var(--mm-signal)] text-[var(--mm-navy)]' : 'text-muted-foreground border-transparent'}`}
          >
            {item === 'login' ? '登录' : '注册'}
          </button>
        ))}
      </div>
      <div>
        <label htmlFor="email" className="text-foreground text-sm font-medium">
          邮箱
        </label>
        <Input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          placeholder="name@example.com"
          aria-invalid={Boolean(errors.email)}
          aria-describedby={errors.email ? 'email-error' : undefined}
          className="bg-card mt-2 h-11"
        />
        {errors.email && (
          <p id="email-error" className="text-destructive mt-1.5 text-xs">
            {errors.email}
          </p>
        )}
      </div>

      <div>
        <label
          htmlFor="password"
          className="text-foreground text-sm font-medium"
        >
          密码
        </label>
        <div className="relative mt-2">
          <Input
            id="password"
            name="password"
            type={showPassword ? 'text' : 'password'}
            autoComplete={
              mode === 'register' ? 'new-password' : 'current-password'
            }
            maxLength={128}
            aria-invalid={Boolean(errors.password)}
            aria-describedby={errors.password ? 'password-error' : undefined}
            className="bg-card h-11 pr-11"
          />
          <button
            type="button"
            onClick={() => setShowPassword((visible) => !visible)}
            className="text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:ring-ring absolute top-1/2 right-1 flex size-9 -translate-y-1/2 items-center justify-center rounded-md focus-visible:ring-2 focus-visible:outline-none"
            aria-label={showPassword ? '隐藏密码' : '显示密码'}
          >
            {showPassword ? (
              <EyeOff className="size-4" />
            ) : (
              <Eye className="size-4" />
            )}
          </button>
        </div>
        {errors.password && (
          <p id="password-error" className="text-destructive mt-1.5 text-xs">
            {errors.password}
          </p>
        )}
      </div>

      {mode === 'register' && (
        <div>
          <label
            htmlFor="confirm-password"
            className="text-foreground text-sm font-medium"
          >
            确认密码
          </label>
          <Input
            id="confirm-password"
            name="confirmPassword"
            type="password"
            autoComplete="new-password"
            maxLength={128}
            className="bg-card mt-2 h-11"
          />
          <p className="text-muted-foreground mt-2 text-xs leading-5">
            密码至少 15 个字符，建议使用容易记住的长短语。
          </p>
        </div>
      )}

      {errors.form && (
        <p
          role="alert"
          className="border border-[#e4b8aa] bg-[#fff7f4] px-3 py-2.5 text-sm text-[#8f351d]"
        >
          {errors.form}
        </p>
      )}
      {mutation.isError && (
        <p role="alert" className="text-destructive text-sm">
          {mutation.error.message}
        </p>
      )}

      <Button
        type="submit"
        size="lg"
        className="h-11 w-full"
        disabled={mutation.isPending}
      >
        {mutation.isPending
          ? '正在处理…'
          : mode === 'login'
            ? '登录'
            : '注册并登录'}
      </Button>

      <p className="text-muted-foreground text-xs leading-5">
        百科资料无需登录，账号用于 AI 问答。注册后自动登录当前设备。
      </p>
    </form>
  )
}
