#!/usr/bin/env node

const { randomBytes } = require('node:crypto')
const { access, readFile, writeFile } = require('node:fs/promises')
const path = require('node:path')
const { parseArgs, parseEnv } = require('node:util')

async function exists(filename) {
  try {
    await access(filename)
    return true
  } catch (error) {
    if (error.code === 'ENOENT') return false
    throw error
  }
}

function setValue(contents, key, value) {
  const pattern = new RegExp(`^${key}=.*$`, 'm')
  if (!pattern.test(contents)) throw new Error(`示例配置缺少 ${key}`)
  return contents.replace(pattern, () => `${key}=${value}`)
}

function requiredValue(values, key) {
  const value = values[key]
  if (!value) throw new Error(`数据库配置缺少 ${key}，请检查 infra/env/.env`)
  return value
}

async function chooseModel(baseUrl, suppliedModel) {
  if (suppliedModel !== undefined) {
    if (!/^[A-Za-z0-9_./:@+-]{1,200}$/.test(suppliedModel)) {
      throw new Error('模型名格式不正确，请使用 ollama list 显示的完整名称')
    }
    return suppliedModel
  }
  let response
  try {
    response = await fetch(`${baseUrl.replace(/\/$/, '')}/models`, {
      signal: AbortSignal.timeout(5000),
    })
  } catch {
    throw new Error(
      '无法读取本地模型列表，请启动 Ollama，或使用 --model 指定模型名',
    )
  }
  if (!response.ok)
    throw new Error(`模型列表请求失败（HTTP ${response.status}）`)
  const payload = await response.json()
  if (
    !payload ||
    typeof payload !== 'object' ||
    !Array.isArray(payload.data) ||
    payload.data.some((item) => typeof item?.id !== 'string')
  ) {
    throw new Error('模型服务返回了无效的模型列表')
  }
  const models = [...new Set(payload.data.map((item) => item.id))]
  if (models.length === 0)
    throw new Error('没有找到已安装的模型，请先通过 ollama list 核对')
  let model
  if (models.length === 1) {
    model = models[0]
  } else {
    const { default: inquirer } = await import('inquirer')
    const answer = await inquirer.prompt([
      {
        type: 'list',
        name: 'model',
        message: '选择问答模型：',
        choices: models.map((name) => ({ name, value: name })),
      },
    ])
    model = answer.model
  }
  return chooseModel(baseUrl, model)
}

/** 创建缺失的本地配置，凭据只写入被 Git 忽略的文件。 */
async function prepareLocalEnvironment(
  root,
  suppliedModel,
  suppliedPort = '8000',
) {
  if (
    !/^[0-9]+$/.test(suppliedPort) ||
    Number(suppliedPort) < 1 ||
    Number(suppliedPort) > 65535
  ) {
    throw new Error('后端端口必须是 1–65535 之间的整数')
  }
  const infraFile = path.join(root, 'infra/env/.env')
  const serverFile = path.join(root, 'apps/backend/server/.env')
  const clientFile = path.join(root, 'apps/frontend/client/.env.local')
  const infraExists = await exists(infraFile)
  const serverExists = await exists(serverFile)
  if (serverExists && !infraExists) {
    throw new Error(
      '后端配置已存在，但缺少 infra/env/.env。请先根据原 DATABASE_URL 补齐数据库配置，再运行初始化。',
    )
  }
  const clientExists = (
    await Promise.all(
      ['.env.local', '.env', '.env.development', '.env.development.local'].map(
        (name) => exists(path.join(root, 'apps/frontend/client', name)),
      ),
    )
  ).some(Boolean)
  const created = []
  const preserved = []
  const pending = []
  let apiPort = suppliedPort

  let infra = ''
  if (infraExists) {
    preserved.push('infra/env/.env')
    if (!serverExists) infra = await readFile(infraFile, 'utf8')
  } else {
    infra = await readFile(`${infraFile}.example`, 'utf8')
    infra = setValue(
      infra,
      'POSTGRES_PASSWORD',
      randomBytes(32).toString('hex'),
    )
    pending.push({ filename: infraFile, contents: infra })
  }

  if (serverExists) {
    preserved.push('apps/backend/server/.env')
    if (!clientExists)
      apiPort = parseEnv(await readFile(serverFile, 'utf8')).API_PORT ?? '8000'
  } else {
    let server = await readFile(`${serverFile}.example`, 'utf8')
    const infraValues = parseEnv(infra)
    const username = requiredValue(infraValues, 'POSTGRES_USER')
    const password = requiredValue(infraValues, 'POSTGRES_PASSWORD')
    const database = requiredValue(infraValues, 'POSTGRES_DB')
    const port = requiredValue(infraValues, 'POSTGRES_PORT')
    if (!/^[0-9]+$/.test(port) || Number(port) < 1 || Number(port) > 65535)
      throw new Error('POSTGRES_PORT 必须是有效端口')
    const defaults = parseEnv(server)
    const model = await chooseModel(defaults.AI_BASE_URL, suppliedModel)
    const url = `postgresql+psycopg://${encodeURIComponent(username)}:${encodeURIComponent(password)}@127.0.0.1:${port}/${encodeURIComponent(database)}`
    server = setValue(server, 'DATABASE_URL', url)
    server = setValue(server, 'AI_MODEL', model)
    server = setValue(server, 'API_PORT', apiPort)
    pending.push({ filename: serverFile, contents: server })
  }

  if (clientExists) {
    preserved.push('apps/frontend/client/已有环境配置')
  } else {
    const template = await readFile(
      path.join(root, 'apps/frontend/client/.env.example'),
      'utf8',
    )
    if (
      !/^[0-9]+$/.test(apiPort) ||
      Number(apiPort) < 1 ||
      Number(apiPort) > 65535
    )
      throw new Error('后端配置中的 API_PORT 不是有效端口')
    const contents = setValue(
      template,
      'API_BASE_URL',
      `http://127.0.0.1:${apiPort}`,
    )
    pending.push({ filename: clientFile, contents })
  }

  for (const item of pending) {
    // 排他创建避免并发执行时覆盖已有配置。
    await writeFile(item.filename, item.contents, { flag: 'wx', mode: 0o600 })
    created.push(path.relative(root, item.filename))
  }
  return { created, preserved }
}

async function main() {
  const { values } = parseArgs({
    options: {
      model: { type: 'string' },
      port: { type: 'string' },
      help: { type: 'boolean', short: 'h' },
    },
  })
  if (values.help) {
    console.log(
      '用法：pnpm dev:setup [--model 模型名] [--port 后端端口]\n创建缺失的本地配置并保留已有配置。模型默认从 Ollama 的已安装列表选择，后端端口默认 8000。',
    )
    return
  }
  const result = await prepareLocalEnvironment(
    path.resolve(__dirname, '..'),
    values.model,
    values.port,
  )
  for (const filename of result.created) console.log(`已创建：${filename}`)
  for (const filename of result.preserved) console.log(`已保留：${filename}`)
  console.log(
    '\n接下来依次运行：\n  docker compose --env-file infra/env/.env -f infra/compose.yaml up -d --wait db\n  pnpm --dir apps/backend/server exec uv run --locked alembic upgrade head\n  pnpm dev:check\n  pnpm dev:all\n\n已运行的后端需要重启才能加载新配置。',
  )
}

module.exports = { prepareLocalEnvironment }

if (require.main === module) {
  main().catch((error) => {
    console.error(`配置初始化失败：${error.message}`)
    process.exitCode = 1
  })
}
