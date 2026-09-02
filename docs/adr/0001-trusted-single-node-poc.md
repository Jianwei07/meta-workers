# Use a trusted single-node coworker architecture

Meta Workers extracts the useful OpenWorker runtime contracts into one FastAPI service, stores logical user partitions in SQLite, and runs tools in per-user Docker computers. Authentication, secure SaaS tenancy, Postgres, queues, and distributed workers are deferred because this release proves the coworker workflow; the UI must label that boundary explicitly.
