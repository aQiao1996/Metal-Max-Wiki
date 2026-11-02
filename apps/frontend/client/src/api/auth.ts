import { z } from 'zod'

import { ApiError, request } from '@/lib/request'

export const userSchema = z.object({ id: z.uuid(), email: z.email() })
export type CurrentUser = z.infer<typeof userSchema>
export const currentUserKey = ['current-user'] as const

/** 查询服务器会话，只有 401 表示尚未登录。 */
export async function getCurrentUser(): Promise<CurrentUser | null> {
  try {
    return await request('/api/v1/auth/me', userSchema)
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null
    throw error
  }
}

/** 创建或恢复 Cookie 登录会话。 */
export function authenticate(
  mode: 'login' | 'register',
  email: string,
  password: string,
) {
  return request(`/api/v1/auth/${mode}`, userSchema, {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
}

/** 注销当前会话。 */
export function logout() {
  return request('/api/v1/auth/logout', z.null(), { method: 'POST' })
}
