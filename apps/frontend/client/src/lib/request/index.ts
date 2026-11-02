import { z } from 'zod'

const errorSchema = z.object({ code: z.number(), message: z.string() })

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message)
    this.name = 'ApiError'
  }
}

/** 请求接口并在边界校验数据结构。 */
export async function request<T>(
  url: string,
  schema: z.ZodType<T>,
  options: RequestInit = {},
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      cache: 'no-store',
      credentials: 'same-origin',
      ...options,
      headers: { 'Content-Type': 'application/json', ...options.headers },
    })
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw error
    throw new ApiError(503, '暂时无法连接服务，请稍后重试。')
  }
  if (!response.headers.get('content-type')?.includes('application/json')) {
    throw new ApiError(
      response.status,
      '服务未返回有效数据，请确认后端已启动。',
    )
  }
  const payload: unknown = await response.json()
  if (!response.ok) {
    const result = errorSchema.safeParse(payload)
    throw new ApiError(
      response.status,
      result.success ? result.data.message : '请求处理失败。',
    )
  }
  const envelope = z
    .object({ code: z.literal(200), data: schema, message: z.string() })
    .safeParse(payload)
  if (!envelope.success)
    throw new ApiError(502, '接口数据格式不正确，请联系站点维护者。')
  return envelope.data.data
}
