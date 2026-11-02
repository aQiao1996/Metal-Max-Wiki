import path from 'node:path'

import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  agentRules: false,
  output: process.env.NODE_ENV === 'production' ? 'standalone' : undefined,
  outputFileTracingRoot: path.join(__dirname, '../../..'),
  // 覆盖后端模型调用允许的最长 300 秒超时。
  experimental: { proxyTimeout: 330000 },
  async rewrites() {
    const origin = (
      process.env.API_BASE_URL ?? 'http://127.0.0.1:8000'
    ).replace(/\/$/, '')
    return [{ source: '/api/:path*', destination: `${origin}/api/:path*` }]
  },
}

export default nextConfig
