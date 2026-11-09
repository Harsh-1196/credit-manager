import { execSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendDir = path.resolve(__dirname, '..');
const rootDir = path.resolve(frontendDir, '..');
const backendDir = path.join(rootDir, 'backend');

console.log('Generating OpenAPI schema from FastAPI backend...');
const exportCmd = `python -c "import json; from app.main import app; from pathlib import Path; Path(r'${path.join(frontendDir, 'openapi.json')}').write_text(json.dumps(app.openapi(), indent=2), encoding='utf-8')"`;

try {
  execSync(exportCmd, { cwd: backendDir, stdio: 'inherit' });
  console.log('Exported openapi.json successfully.');

  console.log('Generating TypeScript types via openapi-typescript...');
  const openapiTsCmd = `npx openapi-typescript "${path.join(frontendDir, 'openapi.json')}" -o "${path.join(frontendDir, 'src', 'lib', 'api', 'schema.ts')}"`;
  execSync(openapiTsCmd, { cwd: frontendDir, stdio: 'inherit' });
  console.log('Generated src/lib/api/schema.ts successfully.');
} catch (err) {
  console.error('Failed to generate API client:', err);
  process.exit(1);
}
