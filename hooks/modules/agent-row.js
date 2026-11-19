// AgentRow body renderer: ports the pure row formatting of coordinator/bin/subagent-statusline.py
// to a plugin hooks module (ui.render on the AgentRow render site). Pure function of e.props:
// no file, env, `$` or process access per render; the module runtime has no Node.
//
// Dropped against the python source: the compaction percentage (needs the settings env and
// compaction_defaults) and the session-effort file fallback (a file read per row).
// Failure mode is blank, never loud: malformed input passes the event through unchanged.
// A body of "" hides the row, so a render that yields nothing never sets one.

const SEP = ' · ';
const ELLIPSIS = '…';
const GENERIC_KINDS = new Set(['local_agent']);
const IDENTITY_CAP = 32;

const isNum = (v) => typeof v === 'number' && Number.isFinite(v);
const isText = (v) => typeof v === 'string' && v.trim() !== '';
const squash = (s) => s.trim().split(/\s+/).join(' ');
// Code-point aware, matching python's str slicing.
const cut = (s, n) => Array.from(s).slice(0, n).join('');
const len = (s) => Array.from(s).length;

export function identity(props) {
  for (const key of ['name', 'label', 'type']) {
    const value = props[key];
    if (!isText(value)) continue;
    if (GENERIC_KINDS.has(value.trim().toLowerCase())) continue;
    let out = squash(value);
    if (len(out) > IDENTITY_CAP) out = cut(out, IDENTITY_CAP - 1) + ELLIPSIS;
    return out;
  }
  return null;
}

export function activity(props) {
  return isText(props.description) ? squash(props.description) : null;
}

export function elapsedSegment(startTime, nowMs) {
  if (!isNum(startTime) || !isNum(nowMs)) return null;
  const startMs = startTime > 1e11 ? startTime : startTime * 1000;
  const seconds = Math.trunc((nowMs - startMs) / 1000);
  if (seconds < 0) return null;
  if (seconds < 60) return `${seconds}s`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m${String(seconds % 60).padStart(2, '0')}s`;
  return `${Math.floor(minutes / 60)}h${String(minutes % 60).padStart(2, '0')}m`;
}

export function tokensSegment(tokenCount) {
  if (!isNum(tokenCount) || tokenCount < 0) return null;
  if (tokenCount < 1000) return String(Math.trunc(tokenCount));
  if (tokenCount < 1e6) return `${(tokenCount / 1000).toFixed(1)}k`;
  return `${(tokenCount / 1e6).toFixed(1)}M`;
}

export function modelSegment(model) {
  if (!isText(model)) return null;
  const m = model.trim();
  return (m.startsWith('claude-') ? m.slice('claude-'.length) : m) || null;
}

export function effortSegment(effort) {
  if (isText(effort)) return effort.trim();
  return isNum(effort) ? String(effort) : null;
}

// Row text for one AgentRow props object, or null when nothing is renderable.
// `nowMs` is epoch milliseconds (the elapsed segment drops when absent).
export function renderRow(props, nowMs) {
  const fixed = [];
  const ident = identity(props);
  if (ident) fixed.push(ident);
  for (const seg of [
    modelSegment(props.model),
    effortSegment(props.effort),
    elapsedSegment(props.startTime, nowMs),
    tokensSegment(props.tokenCount),
    isText(props.status) ? props.status.trim() : null,
  ]) {
    if (seg) fixed.push(seg);
  }

  const columns = props.columns;
  const bounded = isNum(columns) && columns >= 0;

  // Activity is the one variable-length segment: it alone absorbs the width squeeze.
  const act = activity(props);
  if (act) {
    const position = ident ? 1 : 0;
    const budget = bounded ? Math.trunc(columns) - (len(fixed.join(SEP)) + len(SEP)) : null;
    if (budget === null || budget >= len(act)) {
      fixed.splice(position, 0, act);
    } else {
      fixed.splice(position, 0, cut(act, Math.max(budget, 2) - 1) + ELLIPSIS);
    }
  }
  if (!fixed.length) return null;

  let content = fixed.join(SEP);
  if (bounded) content = cut(content, Math.trunc(columns));
  return content || null;
}

// Event in, event out: sets props.body, or returns the event unchanged on any malformed input.
export function withBody(e, nowMs) {
  try {
    if (!e || typeof e !== 'object' || !e.props || typeof e.props !== 'object') return e;
    const body = renderRow(e.props, nowMs);
    return body ? { ...e, props: { ...e.props, body } } : e;
  } catch {
    return e;
  }
}

export function register(on) {
  on('ui.render', { component: 'AgentRow' }, async ($, e, next) =>
    next(withBody(e, typeof Date === 'function' ? Date.now() : undefined)));
}
