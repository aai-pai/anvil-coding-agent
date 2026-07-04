import React, { useEffect } from 'react';
import useLocalStorage from './hooks/useLocalStorage';
import TaskInput from './components/TaskInput';
import TaskList from './components/TaskList';
import ThemeToggle from './components/ThemeToggle';

export default function App() {
  const [tasks, setTasks] = useLocalStorage('tasks', []);
  const [theme, setTheme] = useLocalStorage('theme', 'light');

  // Apply the dark class on html element whenever theme changes
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  const addTask = (text) => {
    if (!text.trim()) return;
    const newTask = {
      id: crypto.randomUUID(),
      text: text.trim(),
      completed: false,
    };
    setTasks(prev => [...prev, newTask]);
  };

  const toggleTask = (id) => {
    setTasks(prev =>
      prev.map(task =>
        task.id === id ? { ...task, completed: !task.completed } : task
      )
    );
  };

  const deleteTask = (id) => {
    setTasks(prev => prev.filter(task => task.id !== id));
  };

  const updateTask = (id, newText) => {
    if (!newText.trim()) {
      deleteTask(id);
      return;
    }
    setTasks(prev =>
      prev.map(task =>
        task.id === id ? { ...task, text: newText.trim() } : task
      )
    );
  };

  const toggleTheme = () => {
    setTheme(prev => (prev === 'light' ? 'dark' : 'light'));
  };

  return (
    <main className="min-h-screen flex flex-col items-center justify-start py-12 px-4">
      <div className="w-full max-w-lg">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-4xl font-bold text-gray-800 dark:text-gray-100">
            To-Do
          </h1>
          <ThemeToggle theme={theme} onToggle={toggleTheme} />
        </div>
        <TaskInput onAdd={addTask} />
        <TaskList
          tasks={tasks}
          onToggle={toggleTask}
          onDelete={deleteTask}
          onUpdate={updateTask}
        />
      </div>
    </main>
  );
}