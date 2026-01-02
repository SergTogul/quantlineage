export function money(value) {
  const sign = value < 0 ? '-' : ''; const n = Math.abs(value)
  if (n >= 1_000_000) return `${sign}$${(n / 1_000_000).toFixed(2)}M`
  if (n >= 1_000) return `${sign}$${(n / 1_000).toFixed(1)}K`
  return `${sign}$${n.toFixed(0)}`
}
export function topContributors(items, count = 5) { return [...items].sort((a,b)=>b.risk_amount-a.risk_amount).slice(0,count) }
export function worstStress(items) { return items.length ? items.reduce((w,c)=>c.pnl<w.pnl?c:w) : null }
export function limitStatus(item) { if(item.breached)return'BREACH'; if(item.utilization_pct>=80)return'WARN'; return'OK' }
export function threatClass(level) { return String(level||'LOW').toLowerCase() }
export function percent(value,digits=1){ return `${(value*100).toFixed(digits)}%` }
export function stressSummary(report){ if(!report||!report.evaluations?.length)return{worst:null,severe:0,breaches:0}; return{worst:report.evaluations[0],severe:report.severe_count,breaches:report.breach_count} }
export function topFactors(items,count=8){ return [...items].sort((a,b)=>Math.abs(b.exposure)-Math.abs(a.exposure)).slice(0,count) }
export function varMethod(report,method){ return report?.methods?.find(x=>x.method===method)||null }
export function hierarchyTradeCount(node){ return !node ? 0 : (node.level==='trade'?1:(node.children||[]).reduce((n,x)=>n+hierarchyTradeCount(x),0)) }
export function scenarioPayload(form){
  return {id:'ui_custom',name:form.name||'Custom Scenario',kind:'custom',equity_shock:Number(form.equity)/100,vol_shock:Number(form.vol)/100,rates_shift_bps:Number(form.rates),fx_shock:Number(form.fx)/100,max_loss_pct:Number(form.limit)/100}
}
