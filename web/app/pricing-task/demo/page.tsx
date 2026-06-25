'use client'

import { useEffect, useMemo, useState } from 'react'

type DemoStep = {
  no: number
  title: string
  verb: string
  color: string
  glow: string
  artifactTitle: string
  artifact: string[]
  reasoning: string[]
}

const STEP_FRAMES = 42
const FRAME_MS = 120

const steps: DemoStep[] = [
  {
    no: 1,
    title: '编码核查',
    verb: '识别清单编码与标准名称',
    color: 'from-sky-300 to-cyan-200',
    glow: 'shadow-cyan-500/30',
    artifactTitle: '标准清单命中',
    artifact: ['原始编码 010103002002', '基准编码 010103002', '标准名称 余方弃置'],
    reasoning: ['读取清单编码前 9 位', '比对国标清单库', '确认清单名称与业务语义一致'],
  },
  {
    no: 2,
    title: '项目特征',
    verb: '补全综合考虑与数量特征',
    color: 'from-amber-300 to-orange-200',
    glow: 'shadow-amber-500/30',
    artifactTitle: '特征结构化',
    artifact: ['运输方式 机械装车', '运距 30km', '弃置方式 综合考虑'],
    reasoning: ['抽取项目特征文本', '识别关键数量：30km', '保留后续组合换算所需特征值'],
  },
  {
    no: 3,
    title: '标准工序',
    verb: '拉取清单标准施工工序',
    color: 'from-indigo-300 to-blue-200',
    glow: 'shadow-indigo-500/30',
    artifactTitle: '施工过程',
    artifact: ['装车', '运输', '弃置', '场地清理'],
    reasoning: ['按基准编码查询标准工序', '将工序作为套定额推理约束', '避免候选定额偏离施工场景'],
  },
  {
    no: 4,
    title: '定额候选',
    verb: '检索基础定额候选池',
    color: 'from-slate-200 to-zinc-100',
    glow: 'shadow-slate-400/25',
    artifactTitle: '候选收敛',
    artifact: ['候选 12 条', '剔除组合定额候选', '保留基础子目 120001-210'],
    reasoning: ['根据清单和工序检索候选关系', '过滤组合定额子目', '将候选输入模型进行取舍'],
  },
  {
    no: 5,
    title: '套定额结果',
    verb: '推理并确认基础定额',
    color: 'from-emerald-300 to-lime-200',
    glow: 'shadow-emerald-500/30',
    artifactTitle: '基础定额',
    artifact: ['120001-210', '自卸汽车运土石方 5km以内', '置信度 high'],
    reasoning: ['结合清单特征和候选工作内容', '判断运距基础值为 5km', '输出可确认的基础定额'],
  },
  {
    no: 6,
    title: '人工对比',
    verb: '对比人工套价工程',
    color: 'from-fuchsia-300 to-rose-200',
    glow: 'shadow-fuchsia-500/30',
    artifactTitle: '评测结果',
    artifact: ['命中 1', '遗漏 0', '额外 0', '命中率 100%'],
    reasoning: ['按清单编码对齐人工结果', '比对 AI 定额编码', '形成命中率与差异列表'],
  },
  {
    no: 7,
    title: '组合换算',
    verb: '生成组合定额次数',
    color: 'from-cyan-300 to-teal-200',
    glow: 'shadow-cyan-500/30',
    artifactTitle: '组合定额',
    artifact: ['120001-211', '(30 - 5) / 1 = 25', '追加运输次数 25'],
    reasoning: ['查询 tdek_tzhhs 组合规则', '关联 tdek_tdezm 获取组合定额', '用项目特征 30km 计算追加次数'],
  },
  {
    no: 8,
    title: '系数换算',
    verb: '识别系数规则并标识工料机',
    color: 'from-violet-300 to-purple-200',
    glow: 'shadow-violet-500/30',
    artifactTitle: '完整结果',
    artifact: ['人工费系数 x1.20', '组合定额工料机已合并', '完整组价结果可回看'],
    reasoning: ['读取 tdek_tznhs 换算说明', '从特征中匹配触发条件', '在工料机明细标识作用系数'],
  },
]

const resources = [
  { code: '00010100', name: '普工人工费', type: '人工', factor: 'x1.20' },
  { code: '00010200', name: '技工人工费', type: '人工', factor: 'x1.20' },
  { code: '99073152', name: '新型全密闭式智能泥头车 国V', type: '机械', factor: '-' },
  { code: '120001-211', name: '每增运1km组合定额', type: '组合', factor: '25次' },
]

function classNames(...values: Array<string | false | null | undefined>) {
  return values.filter(Boolean).join(' ')
}

export default function PricingTaskDemoPage() {
  const [frame, setFrame] = useState(0)

  useEffect(() => {
    const timer = window.setInterval(() => setFrame(value => value + 1), FRAME_MS)
    return () => window.clearInterval(timer)
  }, [])

  const activeIndex = Math.floor(frame / STEP_FRAMES) % steps.length
  const activeStep = steps[activeIndex]
  const localFrame = frame % STEP_FRAMES
  const visibleReasoning = activeStep.reasoning.slice(0, Math.min(activeStep.reasoning.length, Math.floor(localFrame / 9) + 1))
  const cycleProgress = ((activeIndex * STEP_FRAMES + localFrame) / (steps.length * STEP_FRAMES)) * 100
  const completedCount = activeIndex

  const metrics = useMemo(
    () => [
      { label: '对比命中率', value: activeIndex >= 5 ? '100%' : '--' },
      { label: '确认定额', value: activeIndex >= 4 ? '1' : '--' },
      { label: '组合次数', value: activeIndex >= 6 ? '25' : '--' },
      { label: '系数规则', value: activeIndex >= 7 ? '1' : '--' },
      { label: '模拟总耗时', value: activeIndex >= 7 ? '41.8s' : `${Math.max(6, activeIndex * 5 + 6)}s` },
    ],
    [activeIndex],
  )

  return (
    <div className="relative min-h-[calc(100vh-7rem)] overflow-hidden rounded-[10px] bg-[#071016] text-slate-100 shadow-2xl shadow-slate-950">
      <div className="absolute inset-0 bg-[linear-gradient(rgba(96,165,250,0.08)_1px,transparent_1px),linear-gradient(90deg,rgba(96,165,250,0.08)_1px,transparent_1px)] bg-[size:38px_38px]" />
      <div className="absolute inset-0 bg-[radial-gradient(circle_at_15%_20%,rgba(34,211,238,0.16),transparent_30%),radial-gradient(circle_at_80%_12%,rgba(245,158,11,0.12),transparent_24%),linear-gradient(135deg,rgba(15,23,42,0.2),rgba(2,6,23,0.92))]" />
      <div className="demo-scanline absolute inset-x-0 top-0 h-px bg-cyan-200/70" />

      <div className="relative z-10 flex min-h-[calc(100vh-7rem)] flex-col p-5 xl:p-6">
        <header className="flex flex-wrap items-start justify-between gap-4 border-b border-white/10 pb-4">
          <div>
            <div className="text-xs font-semibold uppercase tracking-[0.42em] text-cyan-200/80">QMind Pricing Agent</div>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-white xl:text-4xl">单条智能组价编排演示</h1>
            <p className="mt-2 max-w-3xl text-sm text-slate-300">
              从工程清单出发，自动完成编码核查、特征理解、套定额推理、组合换算、系数换算和完整结果沉淀。
            </p>
          </div>
          <div className="w-full max-w-sm rounded-md border border-cyan-300/20 bg-cyan-300/8 px-4 py-3">
            <div className="flex items-center justify-between text-xs text-cyan-100/80">
              <span>自动演示循环</span>
              <span>{activeStep.no}/8</span>
            </div>
            <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full rounded-full bg-cyan-300 transition-all duration-150" style={{ width: `${cycleProgress}%` }} />
            </div>
            <div className="mt-3 text-sm font-medium text-white">{activeStep.title} · {activeStep.verb}</div>
          </div>
        </header>

        <main className="grid min-h-0 flex-1 grid-cols-1 gap-4 py-4 xl:grid-cols-[0.82fr_1.4fr_0.92fr]">
          <section className="flex min-h-0 flex-col gap-4">
            <div className="rounded-md border border-white/10 bg-white/[0.055] p-4 shadow-xl shadow-black/20">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white">工程清单输入</h2>
                <span className="rounded bg-cyan-300/12 px-2 py-1 text-[11px] text-cyan-100">BOQ ITEM</span>
              </div>
              <div className="space-y-3 text-sm">
                <div>
                  <div className="text-xs text-slate-400">清单编码</div>
                  <div className="mt-1 font-mono text-lg text-cyan-100">010103002002</div>
                </div>
                <div>
                  <div className="text-xs text-slate-400">清单名称</div>
                  <div className="mt-1 text-xl font-semibold text-white">余方弃置</div>
                </div>
                <div className="rounded border border-white/10 bg-slate-950/40 p-3">
                  <div className="text-xs text-slate-400">项目特征</div>
                  <div className="mt-2 leading-6 text-slate-200">
                    余方外运，机械装车，运输距离 <span className="font-semibold text-amber-200">30km</span>，弃置方式综合考虑。
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div className="rounded border border-white/10 bg-white/[0.04] p-2">
                    <div className="text-slate-400">计量单位</div>
                    <div className="mt-1 text-white">m3</div>
                  </div>
                  <div className="rounded border border-white/10 bg-white/[0.04] p-2">
                    <div className="text-slate-400">工程量</div>
                    <div className="mt-1 text-white">1280.00</div>
                  </div>
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 rounded-md border border-white/10 bg-black/20 p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white">推理文本流</h2>
                <span className="demo-pulse rounded-full border border-emerald-300/30 px-2 py-0.5 text-[11px] text-emerald-200">streaming</span>
              </div>
              <div className="space-y-2 font-mono text-xs leading-5 text-emerald-100/90">
                {visibleReasoning.map((line, index) => (
                  <div key={`${activeStep.no}-${line}`} className="demo-line" style={{ animationDelay: `${index * 110}ms` }}>
                    <span className="text-cyan-300">&gt;</span> {line}
                  </div>
                ))}
                <div className="inline-block h-4 w-2 animate-pulse bg-emerald-200/80 align-middle" />
              </div>
            </div>
          </section>

          <section className="relative min-h-[520px] overflow-hidden rounded-md border border-white/10 bg-white/[0.045] p-4 shadow-2xl shadow-black/30">
            <div className="relative z-10 flex h-full flex-col">
              <div className="flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-semibold text-white">智能体编排轨道</h2>
                  <p className="mt-1 text-xs text-slate-400">Prompt chain · Tool call · Structured result</p>
                </div>
                <div className="rounded bg-slate-950/60 px-3 py-2 text-right">
                  <div className="text-[11px] text-slate-400">当前阶段</div>
                  <div className="font-mono text-lg text-cyan-100">STEP {String(activeStep.no).padStart(2, '0')}</div>
                </div>
              </div>

              <div className="mt-10 grid flex-1 grid-cols-4 gap-3 content-center">
                {steps.map((step, index) => {
                  const active = index === activeIndex
                  const done = index < activeIndex
                  return (
                    <div
                      key={step.no}
                      className={classNames(
                        'relative min-h-[132px] rounded-md border p-3 transition-all duration-500',
                        active && `scale-[1.03] border-cyan-200/70 bg-slate-900/90 shadow-2xl ${step.glow}`,
                        done && 'border-emerald-300/30 bg-emerald-300/8',
                        !active && !done && 'border-white/10 bg-slate-950/50',
                      )}
                    >
                      <div className={classNames('absolute -top-2 right-3 h-4 w-4 rounded-full', active ? 'demo-node bg-cyan-200' : done ? 'bg-emerald-300' : 'bg-slate-600')} />
                      <div className="text-xs text-slate-400">0{step.no}</div>
                      <div className="mt-2 text-sm font-semibold text-white">{step.title}</div>
                      <div className="mt-2 text-xs leading-5 text-slate-300">{step.verb}</div>
                      <div className="absolute bottom-3 left-3 right-3 h-1 overflow-hidden rounded-full bg-slate-800">
                        <div
                          className={classNames('h-full rounded-full bg-gradient-to-r transition-all duration-500', step.color)}
                          style={{ width: done ? '100%' : active ? `${Math.min(100, (localFrame / STEP_FRAMES) * 100)}%` : '0%' }}
                        />
                      </div>
                    </div>
                  )
                })}
              </div>

              <div className="mt-4 rounded-md border border-cyan-300/20 bg-cyan-300/8 p-4">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div>
                    <div className="text-xs uppercase tracking-[0.24em] text-cyan-100/70">agent action</div>
                    <div className="mt-2 text-xl font-semibold text-white">{activeStep.verb}</div>
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-xs">
                    <div className="rounded bg-black/30 px-3 py-2">
                      <div className="text-slate-400">已完成</div>
                      <div className="mt-1 text-lg font-semibold text-emerald-200">{completedCount}</div>
                    </div>
                    <div className="rounded bg-black/30 px-3 py-2">
                      <div className="text-slate-400">工具调用</div>
                      <div className="mt-1 text-lg font-semibold text-cyan-100">{activeStep.no + 2}</div>
                    </div>
                    <div className="rounded bg-black/30 px-3 py-2">
                      <div className="text-slate-400">结构化产物</div>
                      <div className="mt-1 text-lg font-semibold text-amber-100">{Math.max(1, activeStep.no - 1)}</div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <section className="flex min-h-0 flex-col gap-4">
            <div className="rounded-md border border-white/10 bg-white/[0.055] p-4">
              <div className="mb-3 flex items-center justify-between">
                <h2 className="text-sm font-semibold text-white">当前结构化产物</h2>
                <span className={classNames('rounded bg-gradient-to-r px-2 py-1 text-[11px] font-semibold text-slate-950', activeStep.color)}>
                  {activeStep.title}
                </span>
              </div>
              <div className="rounded border border-white/10 bg-slate-950/40 p-3">
                <div className="text-xs text-slate-400">{activeStep.artifactTitle}</div>
                <div className="mt-3 space-y-2">
                  {activeStep.artifact.map((item, index) => (
                    <div key={item} className="demo-card flex items-center gap-2 rounded bg-white/[0.055] px-3 py-2 text-sm text-slate-100" style={{ animationDelay: `${index * 130}ms` }}>
                      <span className="h-1.5 w-1.5 rounded-full bg-cyan-200" />
                      <span>{item}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            <div className="min-h-0 flex-1 rounded-md border border-white/10 bg-white/[0.045] p-4">
              <h2 className="mb-3 text-sm font-semibold text-white">完整结果预览</h2>
              <div className="space-y-3">
                <div className={classNames('rounded border p-3 transition-all', activeIndex >= 4 ? 'border-emerald-300/30 bg-emerald-300/8' : 'border-white/10 bg-slate-950/40')}>
                  <div className="text-xs text-slate-400">基础定额</div>
                  <div className="mt-1 font-mono text-sm text-emerald-100">120001-210</div>
                  <div className="mt-1 text-xs text-slate-300">自卸汽车运土石方 5km以内</div>
                </div>
                <div className={classNames('rounded border p-3 transition-all', activeIndex >= 6 ? 'border-cyan-300/30 bg-cyan-300/8' : 'border-white/10 bg-slate-950/40')}>
                  <div className="text-xs text-slate-400">组合换算</div>
                  <div className="mt-1 font-mono text-sm text-cyan-100">120001-211 · 25次</div>
                  <div className="mt-1 text-xs text-slate-300">(30km - 5km) / 1km</div>
                </div>
                <div className={classNames('rounded border p-3 transition-all', activeIndex >= 7 ? 'border-violet-300/30 bg-violet-300/8' : 'border-white/10 bg-slate-950/40')}>
                  <div className="text-xs text-slate-400">系数换算</div>
                  <div className="mt-1 text-sm text-violet-100">人工费命中系数 x1.20</div>
                  <div className="mt-1 text-xs text-slate-300">工料机明细保留原含量并标识系数</div>
                </div>
              </div>
            </div>
          </section>
        </main>

        <footer className="grid grid-cols-2 gap-3 border-t border-white/10 pt-4 md:grid-cols-5">
          {metrics.map(metric => (
            <div key={metric.label} className="rounded-md border border-white/10 bg-white/[0.055] px-4 py-3">
              <div className="text-xs text-slate-400">{metric.label}</div>
              <div className="mt-1 text-2xl font-semibold text-white">{metric.value}</div>
            </div>
          ))}
        </footer>

        <div className="mt-4 overflow-hidden rounded-md border border-white/10 bg-slate-950/50">
          <div className="grid grid-cols-[1fr_1.25fr_0.8fr_0.7fr] bg-white/[0.06] px-4 py-2 text-xs text-slate-400">
            <div>编码</div>
            <div>工料机</div>
            <div>类型</div>
            <div>换算</div>
          </div>
          {resources.map((resource, index) => (
            <div key={resource.code} className="grid grid-cols-[1fr_1.25fr_0.8fr_0.7fr] border-t border-white/10 px-4 py-2 text-xs text-slate-200">
              <div className="font-mono text-cyan-100">{resource.code}</div>
              <div>{resource.name}</div>
              <div>{resource.type}</div>
              <div className={index < activeIndex ? 'text-amber-200' : 'text-slate-500'}>{resource.factor}</div>
            </div>
          ))}
        </div>
      </div>

      <style jsx>{`
        .demo-scanline {
          animation: scanline 5.4s linear infinite;
        }
        .demo-node {
          box-shadow: 0 0 0 0 rgba(165, 243, 252, 0.72);
          animation: nodePulse 1.4s ease-out infinite;
        }
        .demo-pulse {
          animation: softPulse 1.6s ease-in-out infinite;
        }
        .demo-line,
        .demo-card {
          opacity: 0;
          transform: translateY(8px);
          animation: revealUp 420ms ease forwards;
        }
        @keyframes scanline {
          0% { transform: translateY(0); opacity: 0; }
          10% { opacity: 0.8; }
          100% { transform: translateY(calc(100vh - 7rem)); opacity: 0; }
        }
        @keyframes nodePulse {
          0% { box-shadow: 0 0 0 0 rgba(165, 243, 252, 0.7); }
          100% { box-shadow: 0 0 0 18px rgba(165, 243, 252, 0); }
        }
        @keyframes softPulse {
          0%, 100% { opacity: 0.65; }
          50% { opacity: 1; }
        }
        @keyframes revealUp {
          to { opacity: 1; transform: translateY(0); }
        }
      `}</style>
    </div>
  )
}
