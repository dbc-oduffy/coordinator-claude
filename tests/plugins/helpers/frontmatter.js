const fs = require('fs');

/**
 * Extract YAML frontmatter from a markdown file.
 * Handles simple key-value pairs, quoted strings, and arrays.
 * No external dependencies — plugin frontmatter is simple enough.
 */
function extractFrontmatter(filePath) {
  const content = fs.readFileSync(filePath, 'utf-8');
  const match = content.match(/^---\r?\n([\s\S]*?)\r?\n---/);
  if (!match) return null;

  const raw = match[1];
  const attrs = {};

  for (const line of raw.split(/\r?\n/)) {
    if (!line.trim() || line.trim().startsWith('#')) continue;

    // Array continuation (- item)
    if (line.match(/^\s+-\s/)) {
      const lastArrayKey = Object.keys(attrs).reverse().find(k => Array.isArray(attrs[k]));
      if (lastArrayKey) {
        attrs[lastArrayKey].push(line.replace(/^\s+-\s*/, '').replace(/^["']|["']$/g, ''));
      }
      continue;
    }

    const colonIdx = line.indexOf(':');
    if (colonIdx === -1) continue;

    const key = line.slice(0, colonIdx).trim();
    let value = line.slice(colonIdx + 1).trim();

    // Strip quotes
    if ((value.startsWith('"') && value.endsWith('"')) ||
        (value.startsWith("'") && value.endsWith("'"))) {
      value = value.slice(1, -1);
    }

    // Inline array: [a, b, c]
    if (value.startsWith('[') && value.endsWith(']')) {
      attrs[key] = value.slice(1, -1).split(',').map(s =>
        s.trim().replace(/^["']|["']$/g, '')
      ).filter(Boolean);
      continue;
    }

    // Empty value followed by array items
    if (value === '') { attrs[key] = []; continue; }

    // Boolean
    if (value === 'true') { attrs[key] = true; continue; }
    if (value === 'false') { attrs[key] = false; continue; }

    // Number
    if (/^\d+$/.test(value)) { attrs[key] = parseInt(value, 10); continue; }

    attrs[key] = value;
  }

  return { attrs, body: content.slice(match[0].length).trim() };
}

module.exports = { extractFrontmatter };
