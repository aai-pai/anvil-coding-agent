---
type: Blueprint
title: "Blueprint \u2014 2026-07-03-modern-to-do-list"
description: 'type: Blueprint'
tags:
- anvil
- blueprint
timestamp: '2026-07-03T23:49:29.421860+00:00'
artifactId: blueprint-v1
phase: blueprint
generatedAt: '2026-07-03T23:49:29.421860+00:00'
derivedFrom:
- docs/spec.md
- docs/architecture.md
---
# Blueprint

---
type: Blueprint
title: "Blueprint — 2026-07-03-modern-to-do-list"
description: Technical blueprint for the Modern To-Do List application, detailing module structure and implementation plan.
tags:
- anvil
- blueprint
timestamp: '2026-07-03T23:52:00.000000+00:00'
artifactId: blueprint-v1
phase: blueprint
generatedAt: '2026-07-03T23:52:00.000000+00:00'
derivedFrom:
- docs/spec.md
- docs/architecture.md
---

# Blueprint: Modern To-Do List

This blueprint provides the detailed implementation plan for the Modern To-Do List, translating the [specification](/docs/spec.md) and [architecture](/docs/architecture.md) into a concrete file and module structure.

## Module Structure

The project will be organized as a standard React application using a component-based directory structure.

### File Tree
```text
src/
├── components/           # UI Components
│   ├── App.jsx           # Root orchestrator & state manager
│   ├── ThemeToggle.jsx   # Dark/Light mode switcher
│   ├── TaskInput.jsx     # Form for creating new tasks
│   ├── TaskList.jsx      # Container for task items
│   └── TaskItem.jsx      # Individual task row (Edit/Complete/Delete)
├── hooks/                # Custom logic and state persistence
│   └── useLocalStorage.js # Generic hook for sync with Web Storage API
├── styles/               # Global styles and Tailwind config
│   └── index.css         # Tailwind directives and base styles
└── App.jsx               # Entry point (mounting App component)
```

### Component Technical Details

#### `App.jsx`
- **State**: 
  - `tasks`: `Array<{id: string, text: string, completed: boolean}>`
  - `theme`: `'light' | 'dark'`
- **Key Functions**: 
  - `addTask(text)`: Generates UUID and appends new task.
  - `toggleTask(id)`: Flips the `completed` boolean.
  - `deleteTask(id)`: Filters out the task by ID.
  - `updateTask(id, newText)`: Updates the text of a specific task.

#### `useLocalStorage.js`
- **Logic**: A custom hook that takes a key and an initial value. It uses `useEffect` to write to `localStorage` whenever the state changes and initializes the state by reading from `localStorage` on first mount.

#### `TaskItem.jsx`
- **Internal State**: `isEditing` (boolean) to toggle between text display and input field.
- **Interactions**:
  - `onChange` for the checkbox $\rightarrow$ calls `toggleTask`.
  - `onBlur` or `Enter` key in edit mode $\rightarrow$ calls `updateTask`.
  - `onClick` on delete button $\rightarrow$ calls `deleteTask`.

#### `ThemeToggle.jsx`
- **Logic**: Toggles the `theme` state.
- **Side Effect**: Manipulates the `document.documentElement` class list (adding/removing the `.dark` class) to enable Tailwind's `dark:` variant.

## Implementation Roadmap

1. **Project Setup**: Initialize React project and configure Tailwind CSS.
2. **Persistence Layer**: Implement `useLocalStorage` hook for data durability.
3. **Core State**: Build `App` component with basic task CRUD logic.
4. **UI Development**:
   - Build `TaskInput` and `TaskList` (including the empty state).
   - Build `TaskItem` with editing and completion logic.
5. **Theming**: Implement `ThemeToggle` and define the color palette for both modes.
6. **Refinement**: Apply responsive Tailwind classes and ensure accessibility (ARIA labels, semantic HTML).

