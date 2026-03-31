// lib/haiku.js — Claude CLI wrapper for Haiku summarization
import { spawn } from 'child_process';
import { tmpdir } from 'os';

/**
 * Call Claude Haiku via the CLI.
 * Pipes prompt text on stdin (avoids shell escaping issues).
 * Returns { text, tokens, isSkip }.
 */
export async function callHaiku(prompt, { timeout = 120_000 } = {}) {
  return new Promise((resolve, reject) => {
    const args = [
      '-p', '-',          // read prompt from stdin
      '--model', 'haiku',
      '--output-format', 'json',
      '--max-turns', '1',
      '--allowedTools', '',
      '--mcp-config', '{"mcpServers":{}}',
      '--strict-mcp-config'
    ];

    // Strip CLAUDECODE env to allow nested sessions
    const env = { ...process.env };
    delete env.CLAUDECODE;

    const child = spawn('claude', args, {
      cwd: tmpdir(),
      env,
      stdio: ['pipe', 'pipe', 'pipe'],
      timeout
    });

    let stdout = '';
    let stderr = '';

    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });

    child.on('error', err => reject(new Error(`claude CLI error: ${err.message}`)));

    child.on('close', code => {
      if (code !== 0) {
        return reject(new Error(`claude exited with code ${code}: ${stderr.slice(0, 500)}`));
      }

      try {
        const result = parseResponse(stdout);
        resolve(result);
      } catch (err) {
        reject(new Error(`Failed to parse claude response: ${err.message}`));
      }
    });

    // Write prompt and close stdin
    child.stdin.write(prompt);
    child.stdin.end();
  });
}

/**
 * Parse the JSON response from claude CLI.
 * Extracts text, token usage, and SKIP detection.
 */
export function parseResponse(raw) {
  const data = JSON.parse(raw);

  // Extract text from result field
  const text = (data.result || '').trim();

  // Extract tokens (handle both nested and flat layouts)
  const usage = data.usage || {};
  const input = usage.input_tokens || 0;
  const output = usage.output_tokens || 0;
  const cache = usage.cache_read_input_tokens || usage.cache_creation_input_tokens || 0;

  // Cost calculation — prefer CLI-reported cost, fallback to Haiku pricing (as of 2026-03)
  const HAIKU_INPUT_PER_M = 0.80;
  const HAIKU_OUTPUT_PER_M = 4.00;
  const HAIKU_CACHE_PER_M = 0.08;
  const costUsd = data.total_cost_usd != null
    ? data.total_cost_usd
    : ((input - cache) * HAIKU_INPUT_PER_M / 1_000_000 +
       output * HAIKU_OUTPUT_PER_M / 1_000_000 +
       cache * HAIKU_CACHE_PER_M / 1_000_000);

  // SKIP detection
  const isSkip = text.toUpperCase().startsWith('SKIP');

  return {
    text,
    tokens: { input, output, cache, costUsd },
    isSkip
  };
}
