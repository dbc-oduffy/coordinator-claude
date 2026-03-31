// lib/extract.js — Session JSONL parser
import { createReadStream } from 'fs';
import { createInterface } from 'readline';
import { basename } from 'path';
import { findSession } from './paths.js';

/**
 * Count lines in a file by streaming (no full read into memory).
 */
export async function countLines(filePath) {
  return new Promise((resolve, reject) => {
    let count = 0;
    const stream = createReadStream(filePath, { encoding: 'utf8' });
    stream.on('data', chunk => {
      for (let i = 0; i < chunk.length; i++) {
        if (chunk[i] === '\n') count++;
      }
    });
    stream.on('end', () => resolve(count));
    stream.on('error', reject);
  });
}

/**
 * Extract human/agent message pairs from a session JSONL file.
 * Skips metadata, system reminders, and isMeta messages.
 * Condenses tool_use blocks into short summaries.
 */
export async function extractMessages(filePath, skipLines = 0) {
  const messages = [];
  let lineNum = 0;

  const rl = createInterface({
    input: createReadStream(filePath, { encoding: 'utf8' }),
    crlfDelay: Infinity
  });

  for await (const line of rl) {
    if (lineNum++ < skipLines) continue;

    let obj;
    try { obj = JSON.parse(line); }
    catch { continue; }

    const msgType = obj.type;
    if (obj.isMeta || (msgType !== 'user' && msgType !== 'assistant')) continue;

    const content = obj.message?.content;
    if (!content) continue;

    const texts = extractTexts(content);
    if (texts.length > 0) {
      const role = msgType === 'user' ? 'HUMAN' : 'AGENT';
      messages.push({ role, text: texts.join('\n') });
    }
  }

  return messages;
}

/**
 * Extract readable text from message content (string or block list).
 */
function extractTexts(content) {
  const texts = [];

  if (typeof content === 'string') {
    if (content.includes('<system-reminder>') || content.includes('<command-name>') || content.includes('<local-command')) {
      return texts;
    }
    const trimmed = content.trim();
    if (trimmed) texts.push(trimmed);
  } else if (Array.isArray(content)) {
    for (const block of content) {
      if (block.type === 'text') {
        const text = (block.text || '').trim();
        if (text) texts.push(text);
      } else if (block.type === 'tool_use') {
        texts.push(formatToolUse(block));
      }
    }
  }

  return texts;
}

/**
 * Format a tool_use block as [TOOL: Name detail].
 */
function formatToolUse(block) {
  const name = block.name || '?';
  const inp = block.input || {};

  if (['Edit', 'Read', 'Write'].includes(name)) {
    const filePath = inp.file_path || '?';
    const filename = basename(filePath);
    return `[TOOL: ${name} ${filename}]`;
  }
  if (name === 'Bash' || name === 'PowerShell') {
    const cmd = (inp.command || '?').slice(0, 80);
    return `[TOOL: ${name} \`${cmd}\`]`;
  }
  if (name === 'Grep' || name === 'Glob') {
    return `[TOOL: ${name} '${inp.pattern || '?'}']`;
  }
  return `[TOOL: ${name}]`;
}

/**
 * Main extraction entry point.
 * Returns formatted exchanges text + metadata.
 */
export async function extractSession(sessionId, projectDir, { count, showAll, skipToLine } = {}) {
  const filePath = findSession(sessionId, projectDir);
  if (!filePath) throw new Error(`No session found: ${sessionId || 'latest'}`);

  const actualId = basename(filePath, '.jsonl');
  const totalLines = await countLines(filePath);

  let messages;
  if (showAll) {
    messages = await extractMessages(filePath, 0);
  } else if (count != null) {
    messages = await extractMessages(filePath, 0);
    messages = messages.slice(-count);
  } else {
    const skip = skipToLine || 0;
    messages = await extractMessages(filePath, skip);
  }

  // Format as text
  const lines = [`Session: ${actualId}`, `Lines: ${totalLines}`, '='.repeat(60)];
  let humanCount = 0;

  for (const { role, text } of messages) {
    lines.push(`\n[${role}]`);
    lines.push(text);
    lines.push('-'.repeat(40));
    if (role === 'HUMAN') humanCount++;
  }

  return {
    exchanges: lines.join('\n'),
    position: totalLines,
    humanCount,
    messageCount: messages.length,
    sessionId: actualId
  };
}
