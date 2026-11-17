/**
 * 节碳家 · 数值格式化与边界工具（编译产物）
 * 由 src/ts/format.ts 生成，请勿直接修改源码以外的副本。
 * 生成/校验：node scripts/build-ts.js
 */
(function () {
  'use strict';

  function safe(value, fallback) {
    if (fallback === undefined) fallback = 0;
    if (value === null || value === undefined || value === '') return fallback;
    var n = Number(value);
    return Number.isFinite(n) ? n : fallback;
  }

  function clamp(value, min, max) {
    var n = safe(value, min);
    return Math.min(max, Math.max(min, n));
  }

  function num(value, digits) {
    if (digits === undefined) digits = 1;
    var n = safe(value, 0);
    var d = clamp(digits, 0, 4);
    return n.toFixed(d);
  }

  function money(value) {
    var n = safe(value, 0);
    var fixed = Math.abs(n).toFixed(2);
    var parts = fixed.split('.');
    var grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    var sign = n < 0 ? '-' : '';
    return sign + '¥' + grouped + '.' + parts[1];
  }

  function kg(value) {
    var n = safe(value, 0);
    var fixed = Math.abs(n).toFixed(1);
    var parts = fixed.split('.');
    var grouped = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ',');
    return (n < 0 ? '-' : '') + grouped + '.' + parts[1] + ' kg';
  }

  function percent(value, digits) {
    if (digits === undefined) digits = 0;
    var n = safe(value, 0) * 100;
    return n.toFixed(clamp(digits, 0, 2)) + '%';
  }

  var api = { num: num, money: money, kg: kg, percent: percent, clamp: clamp, safe: safe };
  globalThis.JtcFormat = api;
})();
