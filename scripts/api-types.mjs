// Generates the web app's API types from the server's OpenAPI schema:
// apps/web/src/core/api/schema.d.ts. CI fails if the committed file is outdated.
import { execFileSync } from 'node:child_process'
import { mkdirSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

// openapi-typescript still requires TypeScript 5 (this repo uses 6), so it runs in its own npx environment.
const OPENAPI_TYPESCRIPT = 'openapi-typescript@7.13.0'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const schema = join(root, 'node_modules', '.cache', 'zendilohub', 'openapi.json')
const output = join(root, 'apps', 'web', 'src', 'core', 'api', 'schema.d.ts')

mkdirSync(dirname(schema), { recursive: true })
execFileSync('uv', ['run', '--directory', join(root, 'apps', 'server'), 'zendilohub', 'openapi', schema], {
  stdio: 'inherit',
})
execFileSync('npx', ['--yes', OPENAPI_TYPESCRIPT, schema, '--output', output, '--alphabetize'], { stdio: 'inherit' })
execFileSync('npx', ['prettier', '--write', output], { cwd: root, stdio: 'inherit' })
