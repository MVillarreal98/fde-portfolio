# Document Layout Automator

**Problem → Tool → Impact:** Non-technical staff (clerical/ops operators) had to
re-format reference files by hand — fixed-width layouts for downstream ERP and
carrier systems. Zero tolerance for mistakes, constant repetition, and every
"small manual correction" risked breaking a partner feed. I discovered the pain
while watching the process, scoped a minimum viable tool, and delivered a
**Windows desktop application** the team needed no training to use.

## What it does (`C# / .NET 8 WPF`)

- Loads a delimited source file and a **layout profile** (deterministic column
  mapping: target field ← source column, padding, zero-padding, requiredness,
  regex validation, amount formatting, default on empty).
- Applies the profile **deterministically** — same input, same output, every time.
- Validates every row and reports failures with **file line number and reason**
  in plain Spanish, so the operator fixes the detail, not a mystery.
- Writes the target **fixed-width layout** (configurable delimiter) with an
  end-of-run summary: accepted rows, rejected rows, output path.

## The delivery story (the FDE arc)

1. **Discovery** — the manual re-layout of files for downstream systems was the
   single most error-prone daily task; corrections were going to partners late
   and angry.
2. **Scope the MVP** — one screen, two built-in profiles (OXXO-style deposit
   guide, carrier ASN), no config files needed for the common case.
3. **Ship** — single-click transformation with per-row diagnostics; the rules
   live in code (`services/`), reviewed and auditable.
4. **Result** — hand-edited layouts disappeared from the daily routine; the
   operator completes in minutes what was a careful manual session, without
   breaking partner ingestion once after rollout.

## Layout

```
FileLayoutAutomator/
├── App.xaml / App.xaml.cs / MainWindow.xaml(.cs)  WPF single-screen UI
├── models/LayoutProfile.cs        profiles + ColumnMapping definitions
├── services/LayoutTransformer.cs  deterministic mapping + validation engine
├── services/LayoutProfiles.cs     the two built-in profiles
├── data/sample_input.csv          demo file with valid + planted-bad rows
└── tests/LayoutTransformerTests   xunit: padding, defaults, bad rows, amounts
```

## Run / build

```powershell
dotnet build                       # .NET 8 SDK
dotnet run --project FileLayoutAutomator.csproj
dotnet test tests                  # xunit over the deterministic engine
```

A pre-built transformation result on the bundled demo file is committed under
`sample_output/` so reviewers can inspect the exact artifact without building.
