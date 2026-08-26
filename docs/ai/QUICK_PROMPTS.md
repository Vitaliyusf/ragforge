# Minimal Prompts

Once this pack is committed to the repository, use prompts this short.

## Implement a task
```text
Implement RAG-01.
```

## Force the explicit repo rules reminder
```text
Implement RAG-01. Follow repository agent instructions.
```

## Ask for plan only
```text
Plan RAG-01 only. Do not edit files.
```

## Review a finished branch
```text
Review the current branch against its task file. Do not modify.
```

## Fix test failures for current task only
```text
Fix the current task's failing tests only. Do not expand scope.
```

## Verify before manual commit
```text
Final verification for the current task: diff, focused tests, risks, and recommended commit message. Do not commit.
```

## Create a new task file
```text
Create a task spec from this requirement: <one paragraph>. Follow docs/ai/TASK_TEMPLATE.md. Do not implement it.
```

## Important
Do not paste architecture, Git rules, testing rules or security rules into ordinary prompts; they already live in the repository.

## Locate an existing implementation
```text
Use the repository brain to locate the existing implementation for: <request>. Do not edit yet.
```

## Continue from the other agent
```text
Continue from HANDOFF.md. Verify the current diff and referenced memory records before editing.
```

## Record a decision only
```text
Record this durable decision in shared project memory with rationale, do-not-do guidance and revisit conditions. Do not change code.
```

## Record technical debt only
```text
Record this technical debt with evidence, impact and a focused future task. Do not implement it.
```

## Diagnose narrowly
```text
Diagnose: <symptom>. Query the repository brain first, then inspect only the strongest matching paths and direct callers/tests. Do not edit.
```
