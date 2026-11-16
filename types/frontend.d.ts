/**
 * 前端类型声明（供 tsc --checkJs 使用）。
 *
 * 两类内容：
 * 1. 数据契约：服务端返回的方案、措施、政策、碳迹记录的结构。这部分是强检查的，
 *    字段名写错、类型不合会在类型检查阶段报错。
 * 2. DOM 放宽：本项目是零构建单页，元素结构在 index.html 中静态声明，
 *    getElementById 一律返回基类会让类型检查被 50 多个无关报错淹没。
 *    因此这里把 DOM 查询的返回类型放宽为 any，让检查集中在数据流与函数契约上；
 *    元素是否存在、ID 是否对得上，由 tests/smoke_ui.js 的静态检查负责。
 */

interface Document {
  getElementById(elementId: string): any;
  querySelector(selectors: string): any;
  querySelectorAll(selectors: string): any;
}

interface Element {
  querySelector(selectors: string): any;
  querySelectorAll(selectors: string): any;
  closest(selectors: string): any;
}

/** 单条节能措施。 */
interface JtcAction {
  id: string;
  name: string;
  category: string;
  annualKwhSaved: number;
  annualKwhRange?: [number, number];
  annualMoneySaved: number;
  upfrontCost: number;
  paybackMonths: number | null;
  assumption?: string;
  evidenceLabel?: string;
  sourceName?: string;
  sourceUrl?: string;
  sourceNote?: string;
  costNote?: string;
}

/** 一档方案。 */
interface JtcPlan {
  tier: 'light' | 'balanced' | 'deep' | string;
  name: string;
  tagline: string;
  actions: JtcAction[];
  upfrontCost: number;
  monthlyMoneySaved: number;
  annualKwhSaved: number;
  annualMoneySaved: number;
  annualCo2eKg: number;
  paybackMonths: number | null;
  notes?: string[];
}

/** 政策候选匹配结果。 */
interface JtcPolicy {
  id: string;
  title: string;
  region: string;
  status: string;
  statusLabel?: string;
  eligible: boolean;
  benefit?: string;
  requirements?: string[];
  manualChecks?: string[];
  reasons?: string[];
  application?: string;
  validFrom?: string;
  validTo?: string;
  updatedAt?: string;
  isDemo?: boolean;
  sourceName?: string;
  sourceUrl?: string;
  sourceSecondaryUrl?: string;
  sourceRetrievedAt?: string;
  disclaimer?: string;
}

/** /api/energy/plans 的成功响应。 */
interface JtcEnergyResponse {
  success: boolean;
  plans: JtcPlan[];
  policies: JtcPolicy[];
  baseline: {
    monthlyKwh: number;
    annualKwh: number;
    tariff: number;
    tariffSource?: string;
    source?: string;
    isDefault?: boolean;
  };
  budget: number;
  meta?: {
    actionsVersion?: string;
    policiesVersion?: string;
    factorVersion?: string;
    factorKgCo2ePerKwh?: number;
    factorScope?: string;
    factorUrl?: string;
    factorSource?: string;
    tariffUrl?: string;
    policyCoverage?: string[];
    assumptions?: string[];
  };
  coverage?: { message?: string };
}

/** 一条碳迹记录。 */
interface JtcCarbonEntry {
  id: string;
  inputText?: string;
  content: string;
  scene: string;
  createdAt: string;
}

/** AI 开关的本地状态。 */
interface JtcAiState {
  mode: '' | 'llm' | 'local';
  preset: string;
  baseUrl: string;
  model: string;
  remember: boolean;
  key: string;
}
