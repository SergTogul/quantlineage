const BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

async function json(url, options = {}) {
  const res = await fetch(`${BASE}${url}`, {headers: {'Content-Type':'application/json'}, ...options})
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  return res.json()
}

export async function loadDashboard() {
  const portfolio = await json('/portfolio')
  const body = JSON.stringify(portfolio)
  const [summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution] = await Promise.all([
    json('/risk/summary', {method:'POST', body}), json('/risk/stress', {method:'POST', body}),
    json('/risk/stress/evaluate', {method:'POST', body}), json('/risk/contributors', {method:'POST', body}),
    json('/risk/limits', {method:'POST', body}), json('/risk/factors', {method:'POST', body}),
    json('/risk/var', {method:'POST', body}), json('/risk/hierarchy', {method:'POST', body}),
    json('/risk/attribution/demo', {method:'POST', body}),
  ])
  return {portfolio, summary, stress, threats, contributors, limits, factors, varReport, hierarchy, attribution}
}

export function evaluateCustomScenario(portfolio, scenario) {
  return json('/risk/stress/evaluate/custom',{method:'POST',body:JSON.stringify({portfolio,scenarios:[scenario]})})
}
export function reverseStress(portfolio, factor, target_loss_pct) {
  return json('/risk/stress/reverse',{method:'POST',body:JSON.stringify({portfolio,factor,target_loss_pct})})
}
export function askRisk(portfolio, question) {
  return json('/risk/query',{method:'POST',body:JSON.stringify({portfolio,question})})
}
