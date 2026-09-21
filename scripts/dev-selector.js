#!/usr/bin/env node

const { spawnSync } = require('node:child_process')

const Color = {
  client: '\x1b[34mclient 🌐 -->\x1b[0m',
  server: '\x1b[32mserver ⚡ -->\x1b[0m',
}

const processes = {
  client: { name: Color.client, command: 'pnpm dev:client' },
  server: { name: Color.server, command: 'pnpm dev:server' },
}

const choices = [
  { name: '用户端（client）', value: ['client'] },
  { name: '后端服务（server）', value: ['server'] },
  { name: '全部应用', value: ['client', 'server'] },
]

async function main() {
  const { default: inquirer } = await import('inquirer')
  const { selectedProcesses } = await inquirer.prompt([
    {
      type: 'list',
      name: 'selectedProcesses',
      message: '选择要启动的应用：',
      choices,
    },
  ])

  const selected = selectedProcesses.map((key) => processes[key])
  const result = spawnSync(
    'pnpm',
    [
      'exec',
      'concurrently',
      '--kill-others-on-fail',
      '--names',
      selected.map(({ name }) => name).join(','),
      ...selected.map(({ command }) => command),
    ],
    {
      stdio: 'inherit',
    },
  )

  if (result.error) {
    throw result.error
  }

  if (result.signal) {
    process.kill(process.pid, result.signal)
  }

  process.exitCode = result.status ?? 1
}

main().catch((error) => {
  console.error('启动失败：', error)
  process.exitCode = 1
})
