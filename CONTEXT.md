# Meta Workers

Meta Workers is a trusted self-hosted workspace for persistent AI coworkers. The initial product proves the coworker interaction model without claiming secure SaaS tenancy or regulated KYC.

## Language

**Seeded User**:
A demo identity that owns data and a computer within one trusted deployment. It is a logical partition, not an authenticated security identity.
_Avoid_: Tenant, account

**Agent**:
A durable configured coworker with one mission, one conversation, assigned skills, memory, and a permission mode.
_Avoid_: Bot process, worker process

**Run**:
One bounded execution of an Agent, triggered manually or by a Routine.
_Avoid_: Job, task

**Computer**:
The persistent Docker workspace owned by one Seeded User and shared by that user's Agents.
_Avoid_: Host, machine

**Memory**:
A durable user preference or working convention retrieved for an Agent.
_Avoid_: Case fact, training data

**Routine**:
A recurring prompt that starts a fresh Run on a schedule.
_Avoid_: Automation, cron job

**Skill**:
A reviewed, versioned set of internal instructions that can be assigned to Agents.
_Avoid_: Plugin, tool

**Artifact**:
A Run output deliberately exposed for preview or download.
_Avoid_: Temporary file, log
