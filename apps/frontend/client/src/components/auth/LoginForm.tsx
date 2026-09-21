'use client'

import { FormEvent, useState } from 'react'

import { Eye, EyeOff } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface FormErrors {
  email?: string
  password?: string
  form?: string
}

export function LoginForm() {
  const [showPassword, setShowPassword] = useState(false)
  const [errors, setErrors] = useState<FormErrors>({})

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
    }

    if (Object.keys(nextErrors).length === 0) {
      nextErrors.form = '登录服务尚未接入。'
    }

    setErrors(nextErrors)
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="space-y-5">
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
            autoComplete="current-password"
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

      {errors.form && (
        <p
          role="alert"
          className="border border-[#e4b8aa] bg-[#fff7f4] px-3 py-2.5 text-sm text-[#8f351d]"
        >
          {errors.form}
        </p>
      )}

      <Button type="submit" size="lg" className="h-11 w-full">
        登录
      </Button>

      <p className="text-muted-foreground text-xs leading-5">
        账号系统尚未接入，当前页面仅用于确认界面和校验状态。
      </p>
    </form>
  )
}
