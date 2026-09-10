/**
 * Centralized scenario POST contract consumed from the committed OpenAPI snapshot.
 * Not a generated TypeScript client — path/schema pins only (RF-018).
 */
import spec from './openapi-scenario.json'

function requirePost(path) {
  if (!spec.paths?.[path]?.post) {
    throw new Error(`OpenAPI scenario snapshot missing POST ${path}`)
  }
  return path
}

export const PATH_FORMAL_EVALUATE_CUSTOM = requirePost(
  '/api/v1/risk/stress/formal/evaluate/custom',
)
export const PATH_FORMAL_COMPARE = requirePost('/api/v1/risk/stress/formal/compare')
export const PATH_REVERSE_MULTI = requirePost('/api/v1/risk/stress/reverse/multi')

export { spec as scenarioOpenApiSnapshot }
