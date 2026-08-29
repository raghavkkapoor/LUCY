# Lucy

> A local-first, voice-driven computer agent designed to operate your computer the way a human does — by understanding intent, observing the current state, and taking action.

**Lucy is not a chatbot.**
She is an agent intended to turn natural language into real actions across the user's computer.

---

## Overview

Lucy is a personal computer agent built around one core idea:

**You should be able to tell your computer what you want instead of manually operating it.**

Instead of requiring a user to navigate applications, click through menus, search for settings, write scripts, or remember exact commands, Lucy receives a natural-language request and determines how to accomplish it.

For example:

```text
"Play some Radiohead on Spotify."

"Find that C++ video I was watching yesterday and summarize it."

"Create a Google Doc called Project Ideas and put these notes in it."

"Open Netflix."

"Shuffle my liked songs."

"Email Hawken the pictures from yesterday."

"Make a rotating 3D cube in a new window."

```

The long-term goal is much broader:

```text
User intent
     ↓
Lucy understands the task
     ↓
Lucy observes the computer
     ↓
Lucy determines how to accomplish it
     ↓
Lucy acts
     ↓
Lucy observes the result
     ↓
Lucy adapts if necessary
     ↓
Task complete
```

---

# Why Lucy?

Traditional voice assistants are primarily command systems.

They can handle things like:

```text
"Set a timer for 10 minutes."
"What's the weather?"
"Call Mom."
```

But real computer tasks are often not predefined commands.

A user might say:

```text
"Find the document I was working on last week, add the numbers from this email, and send the updated version to John."
```

There isn't necessarily a predefined command for this.

Lucy is designed around the opposite philosophy:

> **Don't script every possible task. Give the agent the tools necessary to figure out the task.**

This makes Lucy fundamentally different from a traditional collection of automation scripts.

---

# Core Philosophy

### Intent over commands

Lucy should understand what the user wants rather than requiring exact phrasing.

### Observation before action

Lucy should determine the current state of the computer before deciding what to do.

### Adaptation over rigid automation

If something changes, Lucy should be able to react instead of simply failing because a predefined sequence no longer matches.

### Local-first

Sensitive processing and computer control should remain local whenever practical.

### Speed

Lucy should feel like an input method, not a remote assistant that requires waiting several seconds for every interaction.

### Modular architecture

Individual capabilities should be replaceable without rebuilding the entire system.

### Proven capabilities

Working abilities should be separated from experimental capabilities so Lucy's actual reliability is measurable.

---

# Architecture

Current high-level architecture:

```text
                    ┌─────────────────────┐
                    │        User         │
                    │  Voice / Text Input │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │   Speech-to-Text    │
                    │       [MODEL]       │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │    Lucy Runtime     │
                    │                     │
                    │ Context / Planning  │
                    │ Task Interpretation │
                    │ State Management    │
                    └──────────┬──────────┘
                               │
                               ▼
                 ┌───────────────────────────┐
                 │       Action Layer        │
                 │                           │
                 │ Playwright / CDP          │
                 │ Windows UI Automation     │
                 │ PowerShell                │
                 │ Python                    │
                 │ APIs                      │
                 │ ADB                       │
                 │ [OTHER TOOLS]             │
                 └─────────────┬─────────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Computer       │
                    │ Apps / Browser / OS │
                    └──────────┬──────────┘
                               │
                               ▼
                    ┌─────────────────────┐
                    │      Observation    │
                    │ Current system state│
                    └──────────┬──────────┘
                               │
                               └──────────────► Lucy
```

---

# The Agent Loop

Lucy is built around an observe → reason → act → observe loop.

Conceptually:

```python
while task_is_active:

    state = observe_computer()

    decision = model.decide(
        goal=user_goal,
        state=state
    )

    action = execute(decision)

    result = observe_result(action)

    if task_complete(result):
        break
```

The important distinction is that Lucy isn't intended to blindly execute a predetermined sequence.

The result of an action becomes part of the next decision.

---

# Computer Control

Lucy uses multiple control mechanisms depending on the environment.

## Browser / Chromium

For Chromium-based applications, Lucy can use:

* CDP
* Playwright
* DOM inspection
* Browser state
* Multiple tabs/windows
* Popups and dynamically created pages

Lucy maintains awareness of the browser rather than treating a single tab as the entire browser.

```text
Browser
 ├── Window
 │    ├── Tab
 │    └── Tab
 │
 ├── Window
 │    └── Tab
 │
 └── Popup
```

### Why CDP?

CDP allows Lucy to connect to an already-running Chromium instance and interact with it programmatically.

Current debugging configuration:

```text
CDP Port: 9223
```

---

# Windows Automation

For applications that don't expose a useful DOM, Lucy can use Windows UI Automation.

Potential control hierarchy:

```text
Lucy
 │
 ├── Browser → CDP / Playwright
 │
 ├── Windows Apps → UI Automation
 │
 ├── Shell → PowerShell
 │
 ├── System → Python / OS APIs
 │
 └── Android → ADB
```

---

# Shell Execution

Lucy can generate commands when shell-level control is the most appropriate tool.

Current execution environment includes:

* PowerShell
* Python
* Windows system APIs
* [FILL IN]
* [FILL IN]

Commands are executed locally and their output can be returned to Lucy as new context.

Example:

```text
Lucy
  ↓
Generate PowerShell
  ↓
Execute locally
  ↓
Capture stdout/stderr
  ↓
Return result
  ↓
Lucy decides next action
```

---

# Voice

Voice is intended to be Lucy's primary interface.

The target experience is:

```text
User speaks
     ↓
Speech recognition
     ↓
Intent detection
     ↓
Task execution
     ↓
Response / action
```

## Speech Recognition

Current / planned:

* [ ] Local speech recognition
* [ ] Whisper
* [ ] Faster-Whisper
* [ ] [MODEL]
* [ ] Streaming transcription
* [ ] Low-latency transcription
* [ ] Voice activity detection
* [ ] Filler-word handling
* [ ] Partial hypotheses
* [ ] [FUTURE IDEA]

### Design requirement

Speech recognition should distinguish between:

```text
"uh... where did I put that document..."
```

and:

```text
"Open the document called project notes."
```

Not everything the microphone hears should become a command.

---

# Intelligence

Lucy uses an LLM as a reasoning component rather than treating the LLM as the entire system.

Current / planned models:

* Ollama
* Qwen
* [MODEL]
* [MODEL]

Target:

```text
Small enough to run locally
        +
Fast enough for interactive use
        +
Capable enough to reason about computer tasks
```

Current target model size:

```text
< 6B parameters
```

Model:

```text
[FILL IN]
```

Quantization:

```text
[FILL IN]
```

Hardware target:

```text
[FILL IN]
```

---

# Context

One of Lucy's most important design problems is maintaining an accurate representation of the user's computer.

The agent should know what is currently happening rather than relying entirely on previous assumptions.

Potential context sources:

```text
Browser state
Open windows
Active application
Current URL
DOM
UI tree
Terminal output
Filesystem
Clipboard
Screenshots
Application state
Previous actions
Task history
User conversation
External API results
```

The goal is:

> **At any given moment, Lucy should have enough context to make a useful next decision.**

---

# Dynamic Computer State

Lucy should not assume that the computer remains static.

Applications can:

* Open new windows
* Open new tabs
* Spawn popups
* Close pages
* Change URLs
* Change their DOM
* Display authentication dialogs
* Trigger operating-system dialogs
* Change state asynchronously

Therefore Lucy tracks dynamic state rather than relying on fixed references.

Example:

```text
Initial state
    ↓
Lucy opens Spotify
    ↓
Spotify creates/changes UI
    ↓
Lucy observes new state
    ↓
Lucy acts on current state
```

---

# Authentication

Authentication is one of the major challenges for general computer agents.

Examples:

```text
OAuth
2FA
CAPTCHAs
Login dialogs
Browser authentication
OS permission dialogs
Device approval
```

Lucy should eventually have a robust strategy for situations where automated control cannot simply proceed.

Current approach:

```text
[FILL IN]
```

Future approach:

```text
[FILL IN]
```

---

# APIs vs UI Automation

Lucy uses the highest-level reliable interface available.

Preferred hierarchy:

```text
Official API
     ↓
Application protocol
     ↓
DOM / CDP
     ↓
UI Automation
     ↓
Mouse / Keyboard
     ↓
Vision-based interaction
```

The exact hierarchy may change depending on the application.

The principle is:

> **Use the most reliable interface available, while retaining lower-level fallbacks.**

---

# Proven Abilities

These are capabilities that have been successfully tested.

## Browser / Web

* [x] Search YouTube
* [x] Play YouTube content
* [x] Summarize a YouTube video
* [x] Open Netflix
* [x] Create Google Docs
* [x] Write Google Docs
* [x] [ADD]

## Spotify

* [x] Play Spotify
* [x] Pause Spotify
* [x] Control Spotify volume
* [x] Shuffle liked songs
* [x] Play an artist
* [x] [ADD]

## System / Development

* [x] Execute PowerShell
* [x] Execute Python
* [x] Capture command output
* [x] Create files
* [x] Generate calendar files
* [x] Run development tools
* [x] [ADD]

## Communication

* [x] Email attachments / pictures
* [ ] General email workflows
* [ ] Calendar management
* [ ] Messaging
* [ ] [ADD]

## Android

* [x] Detect Android device through ADB
* [x] Wake device
* [x] Retrieve accessible device data
* [x] [ADD]

---

# Example Tasks

Lucy should eventually be able to handle tasks such as:

```text
"Open Spotify and play my liked songs."

"Find the C++ video I was watching and summarize it."

"Create a Google Doc called Lucy Ideas."

"Search YouTube for the latest video from [CHANNEL]."

"Open Netflix."

"Email these pictures to Hawken."

"Open Visual Studio and create a new C# project."

"Make a rotating 3D cube."

"Find the file I created yesterday."

"Check my calendar and tell me what I have tomorrow."

"Download the document from this webpage and summarize it."

"Look at the error on my screen and figure out what's wrong."

"Do whatever is necessary to get this working."
```

The final category is especially important.

Lucy should eventually be capable of receiving **goals rather than procedures**.

---

# Goal-Oriented Automation

Traditional automation:

```text
1. Click here
2. Click here
3. Type this
4. Press Enter
5. Click here
```

Lucy:

```text
Goal:
"Upload this file to my Google Drive."
```

Lucy determines:

```text
Where is the file?
        ↓
Is Google Drive open?
        ↓
How can it be accessed?
        ↓
What UI/API is available?
        ↓
Perform upload
        ↓
Verify result
```

This is the core transition from automation to agency.

---

# Failure Recovery

A major Lucy design requirement is recovering from unexpected states.

Examples:

```text
Expected button missing
        ↓
Inspect current UI
        ↓
Find alternative route
        ↓
Continue
```

or:

```text
Action failed
        ↓
Determine why
        ↓
Change strategy
        ↓
Retry
```

Potential failure categories:

* Application changed
* Popup appeared
* Authentication required
* Element disappeared
* Network failure
* Permission denied
* Wrong page
* Unexpected application state
* Command failure
* Model misunderstanding

Current recovery system:

```text
[FILL IN]
```

---

# Task State

Lucy should maintain explicit task state.

Example:

```python
task = {
    "goal": "...",
    "status": "...",
    "steps": [...],
    "observations": [...],
    "errors": [...],
    "artifacts": [...],
}
```

Possible states:

```text
PLANNING
EXECUTING
OBSERVING
WAITING
RECOVERING
COMPLETED
FAILED
CANCELLED
```

---

# Safety

Lucy has direct access to the user's computer, so safety is a first-class architectural requirement.

Potential protections:

* [ ] Destructive-action confirmation
* [ ] Permission system
* [ ] Tool restrictions
* [ ] Application restrictions
* [ ] Filesystem restrictions
* [ ] Command allow/deny lists
* [ ] Sensitive-data handling
* [ ] Authentication boundaries
* [ ] Emergency stop
* [ ] Action logging
* [ ] [ADD]

Lucy should know when it can act autonomously and when it should ask the user.

---

# Privacy

Lucy is designed around a local-first architecture.

Target principles:

```text
Computer data → stays local
Voice → processed locally
Task state → stored locally
Automation → executed locally
```

External services should only receive information when explicitly required by the architecture or user request.

Exceptions:

```text
[FILL IN API / CLOUD SERVICES]
```

---

# Performance

Lucy is intended to feel interactive.

Important metrics:

```text
Speech → transcript latency
Transcript → first action
Action → observation
Observation → next decision
Total task completion time
CPU usage
RAM usage
GPU usage
Model tokens/sec
```

Current benchmarks:

| Metric                     |    Result |
| -------------------------- | --------: |
| Speech recognition latency | [FILL IN] |
| LLM response latency       | [FILL IN] |
| Tokens/sec                 | [FILL IN] |
| Typical task time          | [FILL IN] |
| RAM usage                  | [FILL IN] |
| CPU usage                  | [FILL IN] |

---

# Testing

Lucy is tested using real tasks rather than only unit tests.

Example:

```text
Task:
"Play my liked songs on Spotify."

Expected:
Spotify opens
    ↓
Liked Songs selected
    ↓
Playback begins
    ↓
Success verified
```

Test categories:

### Deterministic Tasks

Tasks where the procedure is well known.

```text
[FILL IN]
```

### General Tasks

Tasks Lucy has not been explicitly scripted for.

```text
[FILL IN]
```

### Recovery Tests

Tasks intentionally designed to produce unexpected states.

```text
[FILL IN]
```

### Long-Horizon Tasks

Tasks requiring multiple independent actions.

```text
[FILL IN]
```

---

# The Real Benchmark

The most important test is not:

> "Can Lucy execute this script?"

It is:

> **"Can Lucy accomplish a task she has never explicitly been scripted to perform?"**

A successful agent should be able to encounter a new task, inspect its environment, determine an approach, execute it, observe the result, and adapt.

Example:

```text
Unknown task
     ↓
Understand goal
     ↓
Explore environment
     ↓
Select tools
     ↓
Execute
     ↓
Observe
     ↓
Recover if necessary
     ↓
Verify completion
```

---

# Project Structure

Current / planned structure:

```text
Lucy/
│
├── main.py
│
├── core/
│   ├── agent.py
│   ├── context.py
│   ├── state.py
│   ├── planner.py
│   └── loop.py
│
├── voice/
│   ├── stt.py
│   ├── vad.py
│   └── audio.py
│
├── models/
│   ├── llm.py
│   └── configuration.py
│
├── tools/
│   ├── browser/
│   ├── windows/
│   ├── shell/
│   ├── filesystem/
│   ├── android/
│   └── [OTHER]
│
├── abilities/
│   ├── spotify/
│   ├── youtube/
│   ├── gmail/
│   ├── google_docs/
│   └── [OTHER]
│
├── tasks/
│   ├── proven/
│   ├── experimental/
│   └── benchmarks/
│
├── config/
│
├── logs/
│
├── tests/
│
└── README.md
```

Actual repository structure:

```text
[FILL IN]
```

---

# Installation

## Requirements

### Hardware

Minimum:

```text
CPU: [FILL IN]
RAM: [FILL IN]
GPU: [FILL IN]
Storage: [FILL IN]
```

Recommended:

```text
CPU: [FILL IN]
RAM: [FILL IN]
GPU: [FILL IN]
Storage: [FILL IN]
```

### Software

```text
Windows 11
Python [VERSION]
Node.js [VERSION]
Git
PowerShell
Ollama
Chrome / Chromium
[OTHER]
```

---

# Setup

Clone the repository:

```bash
git clone [REPOSITORY_URL]
cd Lucy
```

Install dependencies:

```bash
[FILL IN]
```

Install the local model:

```bash
[FILL IN]
```

Configure Lucy:

```bash
[FILL IN]
```

Start Lucy:

```bash
[FILL IN]
```

---

# Configuration

Example configuration:

```yaml
model:
  provider: ollama
  model: [MODEL]

voice:
  enabled: true
  engine: [ENGINE]

browser:
  cdp_port: 9223

automation:
  playwright: true
  windows_uia: true
  powershell: true

privacy:
  local_only: true
```

Actual configuration:

```text
[FILL IN]
```

---

# Roadmap

## Phase 1 — Foundation

* [x] Core agent loop
* [x] Shell execution
* [x] Browser automation
* [x] CDP integration
* [x] Playwright integration
* [x] Dynamic browser state
* [x] Basic task execution
* [x] Proven task system

## Phase 2 — Voice

* [ ] Local speech recognition
* [ ] Low-latency transcription
* [ ] Voice activity detection
* [ ] Filler detection
* [ ] Interruptions
* [ ] Wake word / activation
* [ ] Text-to-speech
* [ ] Streaming interaction

## Phase 3 — General Computer Control

* [ ] Robust Windows UI Automation
* [ ] Screenshot/vision fallback
* [ ] Keyboard/mouse fallback
* [ ] Better application detection
* [ ] OS dialog handling
* [ ] Authentication handling
* [ ] Better failure recovery

## Phase 4 — Persistent Intelligence

* [ ] Long-term memory
* [ ] User preferences
* [ ] Task history
* [ ] Application knowledge
* [ ] Learned workflows
* [ ] Local knowledge base
* [ ] [ADD]

## Phase 5 — General Agent

* [ ] Unknown-task execution
* [ ] Long-horizon tasks
* [ ] Autonomous recovery
* [ ] Self-verification
* [ ] Better planning
* [ ] Cross-application workflows
* [ ] [ADD]

## Phase 6 — [YOUR BIG IDEA]

```text
[FILL IN]
```

---

# Design Goals

Lucy should eventually satisfy the following:

```text
Fast
Local
Reliable
Adaptable
Private
Extensible
Observable
Recoverable
Goal-oriented
```

Most importantly:

> **Lucy should require less knowledge from the user, not more.**

The user shouldn't need to know:

```text
Which application API exists
Which button to press
Which menu contains the setting
Which command performs the operation
Which browser tab contains the page
```

They should only need to know:

```text
What they want.
```

---

# What Lucy Is Not

Lucy is not intended to be:

* A chatbot with a microphone
* A collection of hardcoded macros
* A remote desktop bot
* A simple voice-command system
* A collection of application-specific scripts
* An always-online cloud assistant

The objective is a computer agent capable of reasoning about its environment.

---

# Current Status

```text
Status: [DEVELOPMENT / EXPERIMENTAL / ALPHA]

Core loop:              [STATUS]
Voice:                  [STATUS]
Local LLM:              [STATUS]
Browser automation:     [STATUS]
Windows automation:     [STATUS]
Task planning:          [STATUS]
Failure recovery:       [STATUS]
Memory:                 [STATUS]
Generalization:         [STATUS]
```

Current proven capabilities:

```text
[FILL IN]
```

Current biggest limitation:

```text
[FILL IN]
```

Current highest-priority objective:

```text
[FILL IN]
```

---

# Known Limitations

Lucy currently struggles with:

* [FILL IN]
* [FILL IN]
* [FILL IN]
* Authentication
* Unexpected OS dialogs
* [FILL IN]
* [FILL IN]

These limitations are tracked intentionally rather than hidden.

---

# Philosophy

The long-term objective isn't to create a better collection of automations.

It is to create a computer interface where the boundary between **thinking of an action** and **performing an action** becomes extremely small.

Today:

```text
Think
 ↓
Figure out how
 ↓
Open application
 ↓
Navigate UI
 ↓
Click buttons
 ↓
Type
 ↓
Check result
```

The intended future:

```text
Think
 ↓
Tell Lucy
 ↓
Done
```

---

# Contributing

Lucy is currently:

```text
[FILL IN: PRIVATE / PUBLIC / SELECTIVE / OPEN SOURCE]
```

Contribution policy:

```text
[FILL IN]
```

---

# License

```text
[FILL IN]
```

---

# Author

**[YOUR NAME / HANDLE]**

Project:

**Lucy**

Repository:

```text
[REPOSITORY_URL]
```

---

# Final Objective

```text
                    ┌──────────────────┐
                    │      Human       │
                    └────────┬─────────┘
                             │
                       Natural intent
                             │
                             ▼
                    ┌──────────────────┐
                    │       Lucy       │
                    │                  │
                    │ Understand       │
                    │ Observe           │
                    │ Plan              │
                    │ Act               │
                    │ Verify            │
                    │ Adapt             │
                    └────────┬─────────┘
                             │
                             ▼
                    ┌──────────────────┐
                    │    Computer      │
                    │                  │
                    │ Apps             │
                    │ Browser          │
                    │ Files            │
                    │ OS               │
                    │ Internet         │
                    └──────────────────┘
```

**The goal is simple:**

> Give Lucy a goal. Let Lucy figure out how to accomplish it.
