/**
 * 节碳家 · 数值格式化与边界工具（TypeScript 源码）
 *
 * 这是前端展示层唯一的数字/文本格式化来源。9 个前端模块原本各自实现
 * 舍入与拼接，容易出现口径不一致；此处用带类型的纯函数统一收敛：
 *   - 所有输入先经有限数与区间校验，非数字不再渲染成 NaN / Infinity；
 *   - 数值、金额、碳排、百分比各走独立函数，输出带单位或千分位；
 *   - 纯函数、无 DOM/网络依赖，编译产物可直接被普通 <script> 加载。
 *
 * 编译：node scripts/build-ts.js  →  backend/static/js/generated/format.js
 * 该产物为 ES2021 普通脚本，挂到 window.JtcFormat，零构建、file:// 可用。
 */

/** 数值可选类型：接口可能返回 null / 缺省，统一用 undefined 表示缺失。 */
type MaybeNumber = number | null | undefined;

/** 格式化结果：始终是可直接写入文本节点的字符串。 */
type DisplayText = string;

/** 全局挂载点，避免污染其它命名空间。 */
declare global {
  interface Window {
    JtcFormat?: JtcFormatApi;
  }
}

/** 对外暴露的 API 形状，供 JS 侧与类型门禁共同校验。 */
interface JtcFormatApi {
  num(value: MaybeNumber, digits?: number): DisplayText;
  money(value: MaybeNumber): DisplayText;
  kg(value: MaybeNumber): DisplayText;
  percent(value: MaybeNumber, digits?: number): DisplayText;
  clamp(value: MaybeNumber, min: number, max: number): number;
  safe(value: MaybeNumber, fallback?: number): number;
}

/** 把任意可能为缺失/非法的值收敛为有限数，失败返回 fallback。 */
function safe(value: MaybeNumber, fallback: number = 0): number {
  if (value === null || value === undefined || value === '') return fallback;
  const n: number = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** 限制到 [min, max] 区间，非法输入按 fallback=min 处理。 */
function clamp(value: MaybeNumber, min: number, max: number): number {
  const n: number = safe(value, min);
  return Math.min(max, Math.max(min, n));
}

/** 按指定小数位输出纯数字字符串（不加千分位，便于表格对齐）。 */
function num(value: MaybeNumber, digits: number = 1): DisplayText {
  const n: number = safe(value, 0);
  const d: number = clamp(digits, 0, 4);
  return n.toFixed(d);
}

/** 金额：保留两位小数并加千分位，前面带 ¥。 */
function money(value: MaybeNumber): DisplayText {
  const n: number = safe(value, 0);
  const fixed: string = Math.abs(n).toFixed(2);
  const parts: string[] = fixed.split('.');
  const grouped: string = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  const sign: string = n < 0 ? '-' : '';
  return sign + '¥' + grouped + '.' + parts[1];
}

/** 碳排：kg 为单位，保留一位小数并加千分位。 */
function kg(value: MaybeNumber): DisplayText {
  const n: number = safe(value, 0);
  const fixed: string = Math.abs(n).toFixed(1);
  const parts: string[] = fixed.split('.');
  const grouped: string = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
  return (n < 0 ? '-' : '') + grouped + '.' + parts[1] + ' kg';
}

/** 百分比：输入为 0–1 的小数，输出带 % 的字符串。 */
function percent(value: MaybeNumber, digits: number = 0): DisplayText {
  const n: number = safe(value, 0) * 100;
  return n.toFixed(clamp(digits, 0, 2)) + '%';
}

/** 编译产物挂载点；模块脚本下用 globalThis 兼容浏览器与 Node 测试。 */
const api: JtcFormatApi = { num, money, kg, percent, clamp, safe };
globalThis.JtcFormat = api;

export {};
