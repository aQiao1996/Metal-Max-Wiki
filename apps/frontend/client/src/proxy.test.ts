import { existsSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

import { NextRequest } from 'next/server'
import { describe, expect, it } from 'vitest'

import { config, proxy } from './proxy'

function makeRequest(pathname: string) {
  return new NextRequest(`https://yangyunqiao.top${pathname}`)
}

describe('equipment detail proxy', () => {
  const equipmentId = 'human-weapon-091c6cd1bf'

  it('仅通过根级 not-found 文件提供可复用的 404 UI', () => {
    const appDirectory = fileURLToPath(new URL('./app/', import.meta.url))

    expect(existsSync(`${appDirectory}not-found.tsx`)).toBe(true)
    expect(existsSync(`${appDirectory}errors/not-found/page.tsx`)).toBe(false)
  })

  it('matcher 覆盖 wiki category 并由 proxy 精确识别装备路由', () => {
    expect(config.matcher).toEqual([
      '/v/:version/wiki/:category',
      '/v/:version/wiki/:category/:id',
    ])
  })

  it('放行已生成的可用版本装备详情', () => {
    const response = proxy(
      makeRequest(`/v/mm2r-099/wiki/equipment/${equipmentId}`),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })

  it.each([
    '/v/missing-version/wiki/equipment',
    '/v/mm2r-nex/wiki/equipment',
    `/v/missing-version/wiki/equipment/${equipmentId}`,
    `/v/mm2r-nex/wiki/equipment/${equipmentId}`,
    '/v/mm2r-099/wiki/equipment/missing-equipment-id',
  ])('将无效装备路由重写到 Next 内建 404：%s', (pathname) => {
    const response = proxy(makeRequest(pathname))

    expect(response.status).toBe(404)
    expect(response.headers.get('x-middleware-rewrite')).toBe(
      'https://yangyunqiao.top/_not-found',
    )
  })

  it.each([
    '/v/mm2r-099/wiki/Equipment/missing-equipment-id',
    '/v/mm2r-099/wiki/%65quipment/missing-equipment-id',
  ])('装备 category 变体不能绕过未知 ID 校验：%s', (pathname) => {
    const response = proxy(makeRequest(pathname))

    expect(response.status).toBe(404)
    expect(response.headers.get('x-middleware-rewrite')).toBe(
      'https://yangyunqiao.top/_not-found',
    )
  })

  it.each([
    '/v/mm2r-099/wiki/monsters',
    '/v/mm2r-099/wiki/monsters/missing-monster-id',
    '/v/missing-version/wiki/guides',
  ])('不把其他 wiki 路由误判为装备：%s', (pathname) => {
    const response = proxy(makeRequest(pathname))

    expect(response.status).toBe(200)
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })
})
