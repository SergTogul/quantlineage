/** Display backend dataset identity. Does not infer synthetic vs public. */

export function displayDataSource(payload) {
  if (!payload) return null
  if (payload.data_source_label) return payload.data_source_label
  const id = payload.historical_dataset_id
  if (!id) return null
  const ver = payload.historical_dataset_version
  return ver ? `${id}/${ver}` : String(id)
}
