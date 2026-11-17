"use strict";
/**
 * 节碳家 · 数值格式化与边界工具（TypeScript 源码）
 *
 * 这是前端展示层唯一的数字/文本格式化来源。9 个前端模块原本各自实现
 * 舍入与拼接，容易出现口径不一致；此处用带类型的纯函数统一收敛：
 *   - 所有输入先经有限数与区间校验，非数字不再渲染成 NaN / Infinity；
 *   - 数值、金额、碳排、百分比各走独立函数，输出带单位或千分位；
 *   - 纯函数、无 DOM/网络依赖，编译产物可直接被普通 <script> 加载。
 *
 * 编译：node scripts/build-ts.js（内部调用 tsc）→ backend/static/js/generated/format.js
 * 该文件刻意不使用 import/export，编译产物是 IIFE 普通脚本，挂到 window.JtcFormat，
 * 从而保持项目零构建、file:// 双击可用的特性。
 */
/** 把全局对象收窄为可挂载类型。 */
function host() {
    return globalThis;
}
(() => {
    'use strict';
    /** 把任意可能为缺失/非法的值收敛为有限数，失败返回 fallback。 */
    function safe(value, fallback = 0) {
        if (value === null || value === undefined)
            return fallback;
        const raw = value;
        if (typeof raw === 'string' && raw.trim() === '')
            return fallback;
        const n = Number(raw);
        return Number.isFinite(n) ? n : fallback;
    }
    /** 限制到 [min, max] 区间，非法输入按 fallback=min 处理。 */
    function clamp(value, min, max) {
        const n = safe(value, min);
        return Math.min(max, Math.max(min, n));
    }
    /** 按指定小数位输出纯数字字符串（不加千分位，便于表格对齐）。 */
    function num(value, digits = 1) {
        const n = safe(value, 0);
        const d = clamp(digits, 0, 4);
        return n.toFixed(d);
    }
    /** 金额：保留两位小数并加千分位，前面带 ¥。 */
    function money(value) {
        const n = safe(value, 0);
        const fixed = Math.abs(n).toFixed(2);
        const parts = fixed.split('.');
        const grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        const sign = n < 0 ? '-' : '';
        return sign + '¥' + grouped + '.' + parts[1];
    }
    /** 碳排：kg 为单位，保留一位小数并加千分位。 */
    function kg(value) {
        const n = safe(value, 0);
        const fixed = Math.abs(n).toFixed(1);
        const parts = fixed.split('.');
        const grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
        return (n < 0 ? '-' : '') + grouped + '.' + parts[1] + ' kg';
    }
    /** 百分比：输入为 0–1 的小数，输出带 % 的字符串。 */
    function percent(value, digits = 0) {
        const n = safe(value, 0) * 100;
        return n.toFixed(clamp(digits, 0, 2)) + '%';
    }
    const api = { num, money, kg, percent, clamp, safe };
    host().JtcFormat = api;
})();
