import test from 'node:test'; import assert from 'node:assert/strict'
import { money, topContributors, worstStress, limitStatus, percent, threatClass, stressSummary, topFactors, varMethod, hierarchyTradeCount, scenarioPayload } from './risk.mjs'
test('money formats institutional-scale values',()=>{assert.equal(money(3_410_000),'$3.41M');assert.equal(money(-81_300),'-$81.3K')})
test('contributors are sorted by risk',()=>assert.deepEqual(topContributors([{risk_amount:2},{risk_amount:10},{risk_amount:3}],2).map(i=>i.risk_amount),[10,3]))
test('worst stress selects most negative pnl',()=>assert.equal(worstStress([{scenario:'a',pnl:-2},{scenario:'b',pnl:-9}]).scenario,'b'))
test('limit status maps breach warning and ok',()=>{assert.equal(limitStatus({breached:true,utilization_pct:101}),'BREACH');assert.equal(limitStatus({breached:false,utilization_pct:85}),'WARN');assert.equal(limitStatus({breached:false,utilization_pct:50}),'OK')})
test('threat helpers format severity and percentages',()=>{assert.equal(percent(.1234),'12.3%');assert.equal(threatClass('SEVERE'),'severe')})
test('stress summary exposes worst scenario and counters',()=>{const report={severe_count:2,breach_count:1,evaluations:[{scenario:'Crash',loss:12}]};assert.deepEqual(stressSummary(report),{worst:report.evaluations[0],severe:2,breaches:1})})
test('factor helpers rank by absolute exposure',()=>assert.equal(topFactors([{factor:'a',exposure:-20},{factor:'b',exposure:10}])[0].factor,'a'))
test('var method selects requested method',()=>assert.equal(varMethod({methods:[{method:'historical',var:1}]},'historical').var,1))
test('hierarchy counts trade leaves',()=>assert.equal(hierarchyTradeCount({level:'portfolio',children:[{level:'trade',children:[]},{level:'book',children:[{level:'trade',children:[]}]}]}),2))
test('scenario builder converts display units to API units',()=>{const x=scenarioPayload({name:'X',equity:-20,vol:50,rates:100,fx:-5,limit:10});assert.equal(x.equity_shock,-.2);assert.equal(x.vol_shock,.5);assert.equal(x.rates_shift_bps,100);assert.equal(x.fx_shock,-.05);assert.equal(x.max_loss_pct,.1)})
