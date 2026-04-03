const fs = require('fs');
const path = require('path');

// Repo root: tests/plugins/helpers/ → 3 levels up
const REPO_ROOT = path.resolve(__dirname, '..', '..', '..');

function fileExists(fp) {
  try { return fs.statSync(fp).isFile(); } catch { return false; }
}

function dirExists(dp) {
  try { return fs.statSync(dp).isDirectory(); } catch { return false; }
}

function readJson(fp) {
  const raw = fs.readFileSync(fp, 'utf-8');
  try { return JSON.parse(raw); } catch (e) { throw new Error(`Invalid JSON in ${fp}: ${e.message}`); }
}

function listFiles(dir, ext) {
  if (!dirExists(dir)) return [];
  return fs.readdirSync(dir).filter(f => {
    if (ext && !f.endsWith(ext)) return false;
    return fs.statSync(path.join(dir, f)).isFile();
  });
}

function listDirs(dir) {
  if (!dirExists(dir)) return [];
  return fs.readdirSync(dir).filter(f =>
    fs.statSync(path.join(dir, f)).isDirectory()
  );
}

/**
 * Get marketplace metadata. Returns null for standalone plugin repos.
 */
function getMarketplace() {
  const mp = path.join(REPO_ROOT, '.claude-plugin', 'marketplace.json');
  if (!fileExists(mp)) return null;
  return { path: mp, dir: REPO_ROOT, data: readJson(mp) };
}

/**
 * Discover plugins in this repo.
 * - Marketplace repo (.claude-plugin/marketplace.json): returns each plugin with string source
 * - Standalone plugin repo (.claude-plugin/plugin.json): returns single plugin at repo root
 */
function getPlugins() {
  const mp = getMarketplace();
  if (mp) {
    return (mp.data.plugins || [])
      .filter(p => typeof p.source === 'string')
      .map(p => ({
        name: p.name,
        dir: path.resolve(REPO_ROOT, p.source),
        marketplaceName: mp.data.name,
      }));
  }
  const pp = path.join(REPO_ROOT, '.claude-plugin', 'plugin.json');
  if (fileExists(pp)) {
    const data = readJson(pp);
    return [{ name: data.name, dir: REPO_ROOT, marketplaceName: null }];
  }
  return [];
}

module.exports = {
  REPO_ROOT,
  fileExists,
  dirExists,
  readJson,
  listFiles,
  listDirs,
  getMarketplace,
  getPlugins,
};
