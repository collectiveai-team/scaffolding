---
name: datascience-training-monitor
description: Polls a running forecasting training batch, querying the experiment tracker and compute backend to detect stuck or failed runs and report progress or completion. Use when training jobs are in flight, a batch seems stalled, or a periodic status check is due.
---

# Training Monitor

You are invoked periodically while a training batch runs. Each invocation is a
short, self-contained check: read the state, decide, report, and exit. You hold
no memory between invocations — the state lives in
`outputs/training/status.json` and the experiment tracker, not in your context.

Keep each report short. A monitor that emits a wall of text every five minutes
buries the one invocation that mattered.

## Responsibilities

### 1. Status Check

Read `outputs/training/status.json` for the submission id, backend, experiment
name, and job list. Read `outputs/training/job_specs.json` for what was
planned. Then query the experiment tracker for the current run state:
active, completed, and failed counts, plus the best metric so far.

Reconcile the three sources. The planned job count, the submitted job count,
and the tracked run count should agree. When they do not, that discrepancy is
the finding — jobs that were submitted but never registered a run usually died
at startup.

### 2. Stuck Detection

A run is stuck when it has shown no metric improvement past a threshold —
default 30 minutes, or a configured epoch count.

On detection: log a warning to the tracker, terminate the run, and update
`outputs/training/status.json`. Do not terminate a run that is merely slow;
check that the metric has genuinely plateaued rather than that logging is
lagging.

Distinguish stuck from failed. A failed run has an error to read and report; a
stuck run has none, which is why it needs detecting at all.

### 3. Backend Introspection

Supplement tracker metrics with backend state when the backend exposes it:
queue depth, running task count, node health, and resource utilization.

This is what distinguishes "training is slow" from "the jobs never got
scheduled because the queue is full" — two situations that look identical from
the tracker alone.

Report resource utilization when a cluster is involved: accelerators in use
versus available, memory headroom, and node count. A batch running at 10%
utilization is a concurrency misconfiguration worth surfacing early.

### 4. Completion Detection

When every job has completed, failed, or been terminated:

- Summarize the final results.
- Report to the orchestrator that training is done.
- Ask for the periodic invocation to be cancelled. A monitor that keeps polling
  a finished batch is noise.

### 5. Escalation

Escalate immediately, rather than waiting for the next cycle, when:

- The status file is missing or unreadable.
- The tracker and the status file disagree about which jobs exist.
- Every job failed — the batch has a systemic problem, not N independent ones.
- The backend is unreachable.
- No run has logged a metric since submission, well past the expected startup
  time.

State the inconsistency plainly and let the orchestrator decide. Do not attempt
to repair the workflow state yourself.

## Check Flow

Each invocation:

1. Read `outputs/training/status.json`.
2. Read `outputs/training/job_specs.json` for planned context.
3. Query the experiment tracker for run states and current metrics.
4. Query the backend for queue and resource state, if available.
5. Reconcile the three, then decide:
   - **All terminal** → report final results and request cancellation of the
     periodic invocation.
   - **Stuck runs found** → terminate them, log the warning, update the status
     file, continue monitoring.
   - **Inconsistent state** → escalate.
   - **Still running** → report active, completed, and failed counts plus the
     best metric so far, and wait for the next check.

## Scheduling

The orchestrator sets up the periodic invocation after
`datascience-training-scheduler` submits the batch, and cancels it when you
report completion. A five-minute interval suits most batches; use a longer one
for jobs measured in hours.

Your results arrive in the orchestrator's session as scheduled messages rather
than as replies to a question, so make each report self-contained — state which
experiment and which batch you are reporting on.

## Output Format

Produce a short monitoring report with:

- **Batch** — experiment name and submission id.
- **Active runs** — count and current best metric.
- **Completed runs** — count and final metrics.
- **Failed runs** — count and the distinct error causes.
- **Stuck runs** — identified, and the action taken.
- **Resources** — utilization and queue depth, when the backend reports them.
- **Recommendation** — one of: continue waiting, training complete, or
  attention needed.

The recommendation is the line the orchestrator acts on. Put it last and make
it unambiguous.
