import { DEFAULT_OVERVIEW_LAYOUT } from '../lib/nav.mjs'
import {
  CommandGoLayout,
  ExceptionQueueLayout,
  FunctionKeysLayout,
  HierarchyBookLayout,
  LaunchpadMosaicLayout,
  OvernightTapeLayout,
  StatusBlotterLayout,
  TwoPaneDeskLayout,
} from './OverviewLayouts.jsx'

const LAYOUTS = {
  status: StatusBlotterLayout,
  desk: TwoPaneDeskLayout,
  queue: ExceptionQueueLayout,
  mosaic: LaunchpadMosaicLayout,
  command: CommandGoLayout,
  hierarchy: HierarchyBookLayout,
  tape: OvernightTapeLayout,
  keys: FunctionKeysLayout,
}

/**
 * Command-center overview. Default composition is the status blotter.
 * Display only — no client risk math.
 */
export default function Overview({
  layout = DEFAULT_OVERVIEW_LAYOUT,
  ...pageProps
}) {
  const Page = LAYOUTS[layout] ? LAYOUTS[layout] : StatusBlotterLayout
  return <Page {...pageProps} />
}
