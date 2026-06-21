import { describe, expect, it } from 'vitest'
import spec from './openapi-scenario.json'
import {
  PATH_FORMAL_COMPARE,
  PATH_FORMAL_EVALUATE_CUSTOM,
  PATH_REVERSE_MULTI,
} from './scenarioApi.js'
import { API_V1 } from '../api.js'

const EVALUATE = `${API_V1}/risk/stress/formal/evaluate/custom`
const COMPARE = `${API_V1}/risk/stress/formal/compare`
const REVERSE_MULTI = `${API_V1}/risk/stress/reverse/multi`

describe('OpenAPI scenario contract snapshot', () => {
  it('pins canonical /api/v1 formal scenario POST paths', () => {
    for (const path of [EVALUATE, COMPARE, REVERSE_MULTI]) {
      expect(spec.paths[path]?.post, path).toBeTruthy()
    }
  })

  it('exports the same POST paths the UI client must call', () => {
    expect(PATH_FORMAL_EVALUATE_CUSTOM).toBe(EVALUATE)
    expect(PATH_FORMAL_COMPARE).toBe(COMPARE)
    expect(PATH_REVERSE_MULTI).toBe(REVERSE_MULTI)
  })

  it('FactorShockWire.amount is bump units (fraction / decimal), not display %', () => {
    const amount = spec.components.schemas.FactorShockWire.properties.amount
    expect(amount.type).toBe('number')
    expect(amount.description.toLowerCase()).toMatch(/relative/)
    expect(amount.description).toMatch(/0\.0001/)
    expect(amount.description.toLowerCase()).toMatch(/decimal/)
  })

  it('ScenarioWire requires typed shocks (not legacy equity_shock scalars)', () => {
    const schema = spec.components.schemas.ScenarioWire
    expect(schema.required).toEqual(expect.arrayContaining(['id', 'name', 'category']))
    expect(schema.properties.shocks).toBeTruthy()
    expect(schema.properties).not.toHaveProperty('equity_shock')
    expect(schema.properties).not.toHaveProperty('rates_shift_bps')
  })

  it('evaluate/compare request bodies are Formal* ScenarioWire wrappers', () => {
    const evalRef = spec.paths[EVALUATE].post.requestBody.content['application/json'].schema.$ref
    const compareRef = spec.paths[COMPARE].post.requestBody.content['application/json'].schema.$ref
    expect(evalRef).toBe('#/components/schemas/FormalCustomStressRequest')
    expect(compareRef).toBe('#/components/schemas/FormalScenarioComparisonRequest')
    expect(spec.components.schemas.FormalCustomStressRequest.properties.scenarios).toBeTruthy()
    expect(spec.components.schemas.FormalScenarioComparisonRequest.properties.scenarios).toBeTruthy()
  })
})
