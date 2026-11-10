import CopilotChat, { CopilotProvider, ModelStatus, useCopilot } from '../components/CopilotChat'
import { PageHeader, Panel } from '../components/ui'
import { useAuth } from '../state/AuthContext'
import { SignInGate } from '../components/Gate'

function CopilotPage() {
  const { state } = useAuth()
  const { status } = useCopilot()
  if (state !== 'in') {
    return <><PageHeader title="Copilot" /><SignInGate what="the copilot" /></>
  }
  return (
    <>
      <PageHeader title="Copilot">
        Ask in plain words: re-solve, validate, compare or explain a plan, or replan after a breakdown, failed delivery or
        urgent order. The model only reads your request; plans come from the solvers and the validator, and replies are
        built from their results.
      </PageHeader>
      <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
        <Panel><CopilotChat /></Panel>
        <aside className="space-y-4 text-sm">
          <Panel title="Model">
            <ModelStatus status={status} />
            {status?.available && <p className="mt-2 text-xs text-ink2">Runs locally. Replies are templates over tool results; numbers no tool produced are blocked.</p>}
          </Panel>
          <Panel title="What it can do">
            <ul className="list-disc space-y-1 pl-4 text-ink2">
              <li>Solve with OR-Tools, the GA or the hybrid</li>
              <li>Validate, compare and explain plans</li>
              <li>Replan after a disruption, only after you press Confirm</li>
            </ul>
            <p className="mt-2 text-xs text-ink2">It never writes routes itself. The copilot is also available as a side panel on every page.</p>
          </Panel>
        </aside>
      </div>
    </>
  )
}

// Inside the console the conversation lives in Layout's provider (shared with the docked panel);
// rendered on its own (tests), the page brings its own provider.
export default function Copilot() {
  return useCopilot() ? <CopilotPage /> : <CopilotProvider><CopilotPage /></CopilotProvider>
}
