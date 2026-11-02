import { z } from 'zod'

import { request } from './index'

/** 服务端通过内部地址调用 FastAPI，不经过浏览器代理。 */
export async function serverRequest<T>(
  path: string,
  schema: z.ZodType<T>,
): Promise<T> {
  const origin = process.env.API_BASE_URL ?? 'http://127.0.0.1:8000'
  return request(`${origin.replace(/\/$/, '')}/api/v1${path}`, schema, {
    signal: AbortSignal.timeout(10000),
  })
}
