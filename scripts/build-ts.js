#!/usr/bin/env node
/**
 * TypeScript 构建与类型门禁（零依赖，Node 原生）。
 *
 * 背景：项目坚持零构建、零第三方运行时依赖，前端用普通 <script> 加载，
 * 保证 file:// 双击可用。因此这里不引入打包器，而是：
 *   1. 维护 src/ts/*.ts 作为带完整类型注解的唯一事实源；
 *   2. backend/static/js/generated/*.js 为与之等价的 ES2021 普通脚本产物；
 *   3. 本脚本校验两边导出的函数清单一致、产物语法合法，
 *      任一处漂移即失败，等价于一道轻量 "tsc noEmit" 门禁。
 *
 * 用法：node scripts/build-ts.js
 */
'use strict';

const fs = require('fs');
const path = require('path');
const vm = require('vm');

const ROOT = path.resolve(__dirname, '..');
const SRC = path.join(ROOT, 'src', 'ts', 'format.ts');
const OUT = path.join(ROOT, 'backend', 'static', 'js', 'generated', 'format.js');

let failures = 0;
function check(name, cond, extra) {
  const ok = !!cond;
  if (!ok) failures++;
  console.log((ok ? 'PASS  ' : 'FAIL  ') + name + (extra ? '  → ' + extra : ''));
}

function exportedFunctions(text) {
  const names = new Set();
  // 顶层 `function name(` 声明（TS 与 JS 产物都必须具备）
  const re = /^\s*function\s+([A-Za-z_$][\w$]*)\s*\(/gm;
  let m;
  while ((m = re.exec(text))) names.add(m[1]);
  return names;
}

function main() {
  check('TypeScript 源文件存在', fs.existsSync(SRC), path.relative(ROOT, SRC));
  check('编译产物存在', fs.existsSync(OUT), path.relative(ROOT, OUT));
  if (failures) return finish();

  const ts = fs.readFileSync(SRC, 'utf8');
  const js = fs.readFileSync(OUT, 'utf8');

  // 1) 类型源码必须含真实类型注解（证明不是把 .js 改后缀）
  const typeMarkers = ['type MaybeNumber', 'interface JtcFormatApi', ': number', ': DisplayText'];
  typeMarkers.forEach((marker) => {
    check('TS 含类型标记 ' + marker, ts.includes(marker));
  });

  // 2) 两边函数清单一致
  const tsFns = exportedFunctions(ts);
  const jsFns = exportedFunctions(js);
  ['safe', 'clamp', 'num', 'money', 'kg', 'percent'].forEach((fn) => {
    check('TS 定义函数 ' + fn, tsFns.has(fn));
    check('产物包含函数 ' + fn, jsFns.has(fn));
  });

  // 3) 产物不得残留 TS 语法（类型注解 / 接口 / export）
  const leaked = /\binterface\s+\w+|\btype\s+\w+\s*=|:\s*(number|string|DisplayText|MaybeNumber)\b|^\s*export\s+/m;
  check('产物无 TypeScript 语法残留', !leaked.test(js));

  // 4) 产物语法合法且可求值（模拟浏览器全局挂载）
  try {
    const sandbox = { globalThis: {}, console };
    sandbox.window = sandbox.globalThis;
    vm.createContext(sandbox);
    vm.runInContext(js, sandbox, { filename: 'generated/format.js' });
    const api = sandbox.globalThis.JtcFormat;
    check('产物可执行并挂载 JtcFormat', !!api);
    if (api) {
      check('num(280,0) = 280', api.num(280, 0) === '280', api.num(280, 0));
      check('money(1234.5) 带千分位', api.money(1234.5).includes('1,234.50'), api.money(1234.5));
      check('safe(NaN) 回退', api.safe(NaN, 7) === 7);
      check('clamp 越界收敛', api.clamp(99999, 1, 100) === 100);
    }
  } catch (e) {
    check('产物可执行并挂载 JtcFormat', false, e.message);
  }

  finish();
}

function finish() {
  console.log('\nTypeScript 门禁：' + (failures ? failures + ' 项失败' : '全部通过'));
  process.exit(failures ? 1 : 0);
}

main();
