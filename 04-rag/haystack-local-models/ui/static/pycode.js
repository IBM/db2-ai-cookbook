"use strict";

// A small Python highlighter. No CDN: the whole point of this recipe is that it runs
// with no internet, so the UI must not reach for a highlighting library either.

const PY_KEYWORDS = ("False None True and as assert async await break class continue def del " +
  "elif else except finally for from global if import in is lambda nonlocal not or pass " +
  "raise return try while with yield").split(" ");

const PY_TOKEN = new RegExp([
  '("""[\\s\\S]*?"""|\'\'\'[\\s\\S]*?\'\'\')',              // 1 triple-quoted strings
  "(#[^\\n]*)",                                              // 2 comments
  '([rbfu]{0,2}"(?:\\\\.|[^"\\\\])*"|[rbfu]{0,2}\'(?:\\\\.|[^\'\\\\])*\')', // 3 strings
  "(@[A-Za-z_][\\w.]*)",                                     // 4 decorators
  "\\b(" + PY_KEYWORDS.join("|") + ")\\b",                   // 5 keywords
  "\\b(\\d+(?:\\.\\d+)?)\\b",                                // 6 numbers
].join("|"), "g");

const CLASS_FOR = { 1: "s doc", 2: "c", 3: "s", 4: "d", 5: "k", 6: "n" };

function escHtml(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

// One pass, so a keyword inside a string is never re-highlighted.
function highlightPython(source) {
  let out = "";
  let last = 0;
  let match;
  PY_TOKEN.lastIndex = 0;
  while ((match = PY_TOKEN.exec(source)) !== null) {
    out += escHtml(source.slice(last, match.index));
    const group = [1, 2, 3, 4, 5, 6].find((i) => match[i] !== undefined);
    out += `<span class="${CLASS_FOR[group]}">${escHtml(match[0])}</span>`;
    last = match.index + match[0].length;
  }
  return out + escHtml(source.slice(last));
}

function codeBlock(source) {
  return `<pre class="code"><code>${highlightPython(source)}</code></pre>`;
}

// The Db2 sample panel shows SQL, not Python, so it gets its own small tokenizer.
const SQL_KEYWORDS = ("SELECT FROM WHERE ORDER BY GROUP HAVING AS AND OR NOT NULL FETCH FIRST " +
  "ROWS ONLY COUNT SUBSTR RETURNING INTEGER VARCHAR CREATE TABLE DROP INSERT INTO VALUES " +
  "JSON_VALUE VECTOR_SERIALIZE VECTOR_DISTANCE COSINE PRIMARY KEY").split(" ");

const SQL_TOKEN = new RegExp([
  "(--[^\\n]*)",                                  // 1 comments
  "('(?:''|[^'])*')",                             // 2 strings
  "\\b(" + SQL_KEYWORDS.join("|") + ")\\b",       // 3 keywords
  "\\b(\\d+)\\b",                                 // 4 numbers
].join("|"), "gi");

function highlightSql(source) {
  let out = "", last = 0, match;
  SQL_TOKEN.lastIndex = 0;
  while ((match = SQL_TOKEN.exec(source)) !== null) {
    out += escHtml(source.slice(last, match.index));
    const group = [1, 2, 3, 4].find((i) => match[i] !== undefined);
    out += `<span class="${{ 1: "c", 2: "s", 3: "k", 4: "n" }[group]}">${escHtml(match[0])}</span>`;
    last = match.index + match[0].length;
  }
  return out + escHtml(source.slice(last));
}

function sqlBlock(source) {
  return `<pre class="code"><code>${highlightSql(source)}</code></pre>`;
}
