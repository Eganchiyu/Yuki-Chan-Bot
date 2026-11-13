/**
 * maid-budget —— 小女仆（DeepSeek Harness 后端）的运行预算插件。
 *
 * 机主要求（2026-11-12）：
 *   1. 单任务最多 30 轮，不允许超过；
 *   2. 时间上限 600s（Yuki 侧的 1020s 等待预算同步收敛到 600s，见 core/maid/maid_common.py）；
 *   3. 读取文件类工具（read / read_image / glob / grep）每次计 0.5 轮，其余工具计 1 轮；
 *   4. 预算用尽后不再继续操作：拒绝一切工具调用，并要求模型立刻总结返回；
 *   5. 每次注入模型提示时都带上「当前第N轮，剩余M轮」。
 *
 * 三个挂载点：
 *   - session/event：按 tool/call 累计已用轮数；turn/start 重置并记录起始时间。
 *   - agent/pre-step：在进入模型请求前追加一条 user 快照消息（预算面板）。
 *   - tools/pre-execute：超轮数/超时后 deny，把「请立刻总结」的反馈交给模型。
 *
 * 失败降级：任何监听器抛错都只记日志，不阻断 agent 循环（宁可没有预算提示，
 * 也不能把整条链路搞崩）。
 */
import z from '@deepseek-ai/schemastery'
import { createUserMessage } from '@deepseek-ai/dsh-llm'

export const name = 'maid-budget'
export const inject = ['agents']

export const Config = z.object({
  /** 单任务最大轮数。 */
  maxRounds: z.number().default(30),
  /** 读取类工具单次计费轮数。 */
  readCost: z.number().default(0.5),
  /** 单任务时间上限（秒）。 */
  timeoutSeconds: z.number().default(600),
  /** 视为「阅读文件操作」的工具名。 */
  readTools: z.array(z.string()).default(['read', 'read_image', 'glob', 'grep']),
  /** 剩余多少轮开始催促收尾。 */
  warnRounds: z.number().default(3),
})

const warned = new Set()

function log(...args) {
  try {
    console.log('[maid-budget]', ...args)
  } catch {
    /* 日志失败不影响主流程 */
  }
}

function sessionKey(agent) {
  try {
    const id = agent?.session?.id
    return id === undefined || id === null ? 'default' : String(id)
  } catch {
    return 'default'
  }
}

function fmt(n) {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}

export function apply(ctx, config) {
  const maxRounds = Number(config?.maxRounds ?? 30)
  const readCost = Number(config?.readCost ?? 0.5)
  const timeoutSeconds = Number(config?.timeoutSeconds ?? 600)
  const readTools = new Set(config?.readTools ?? ['read', 'read_image', 'glob', 'grep'])
  const warnRounds = Number(config?.warnRounds ?? 3)

  if (!(maxRounds > 0) || !(timeoutSeconds > 0)) {
    throw new TypeError('maid-budget: maxRounds / timeoutSeconds 必须是正数')
  }

  /** sessionId -> { spent, startedAt } */
  const budgets = new Map()

  const stateOf = (agent) => {
    const key = sessionKey(agent)
    let state = budgets.get(key)
    if (state === undefined) {
      state = { spent: 0, startedAt: null }
      budgets.set(key, state)
    }
    return state
  }

  const elapsedSeconds = (state) =>
    state.startedAt === null ? 0 : (Date.now() - state.startedAt) / 1000

  // 1) 记账：turn/start 重置，tool/call 按工具权重累加。
  ctx.on('session/event', (session, event) => {
    try {
      const key = session?.id === undefined || session?.id === null ? 'default' : String(session.id)
      let state = budgets.get(key)
      if (state === undefined) {
        state = { spent: 0, startedAt: null }
        budgets.set(key, state)
      }
      if (event.type === 'turn/start') {
        state.spent = 0
        state.startedAt = Date.now()
      } else if (event.type === 'tool/call') {
        const cost = readTools.has(event.data?.name) ? readCost : 1
        state.spent += cost
      }
    } catch (error) {
      log('session/event 记账失败:', error?.message ?? error)
    }
  })

  // 2) 每轮请求前注入预算面板：当前第N轮，剩余M轮。
  ctx.on('agent/pre-step', async ({ agent, signal }, next) => {
    const decision = await next()
    if (decision.kind === 'reject' || signal?.aborted) return decision
    try {
      const state = stateOf(agent)
      const round = Math.floor(state.spent) + 1
      const remaining = Math.max(0, maxRounds - state.spent)
      const secondsLeft = Math.max(0, Math.ceil(timeoutSeconds - elapsedSeconds(state)))
      let text =
        `【小女仆运行预算】当前第${fmt(round)}轮，剩余${fmt(remaining)}轮` +
        `（上限 ${maxRounds} 轮；读取类工具计 ${readCost} 轮/次；剩余时间约 ${secondsLeft}s）。`
      if (remaining <= 0 || secondsLeft <= 0) {
        text +=
          '\n预算已用尽：不要再调用任何工具，立刻基于已有信息总结，并直接给出最终结果。'
      } else if (remaining <= warnRounds || secondsLeft <= 30) {
        text += '\n预算即将用尽：停止开新方向，尽快收尾并给出结论。'
      }
      return {
        ...decision,
        messages: [
          ...decision.messages,
          createUserMessage({
            content: [{ type: 'text', text }],
            source: { kind: name, form: 'snapshot', sections: [{ name, text }] },
          }),
        ],
      }
    } catch (error) {
      log('pre-step 注入失败:', error?.message ?? error)
      return decision
    }
  })

  // 3) 超限硬闸：轮数或时间用尽后拒绝一切工具，只允许模型总结。
  ctx.on('tools/pre-execute', async (exec, next) => {
    try {
      const agent = exec?.agent
      if (agent === undefined) return next()
      const state = stateOf(agent)
      const outOfRounds = state.spent >= maxRounds
      const outOfTime = elapsedSeconds(state) >= timeoutSeconds
      if (!outOfRounds && !outOfTime) return next()
      const why = outOfRounds
        ? `轮数预算已用尽（${fmt(state.spent)} / ${maxRounds} 轮）`
        : `时间预算已用尽（${timeoutSeconds}s）`
      if (!warned.has(sessionKey(agent))) {
        warned.add(sessionKey(agent))
        log(`${why}，开始拒绝工具调用`)
      }
      return {
        kind: 'deny',
        reason: `${why}，不再执行工具 ${exec.name}。请立刻停止操作，基于已有信息总结并给出最终结果。`,
      }
    } catch (error) {
      log('pre-execute 拦截失败:', error?.message ?? error)
      return next()
    }
  })
}
