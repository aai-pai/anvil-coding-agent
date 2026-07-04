(function() {
  'use strict';

  // -------------------------------------------------------------
  // StorageManager
  // -------------------------------------------------------------
  const StorageManager = {
    getTasks() {
      try {
        const data = localStorage.getItem('todo-tasks');
        return data ? JSON.parse(data) : [];
      } catch (e) {
        console.warn('Failed to load tasks from localStorage:', e);
        return [];
      }
    },
    saveTasks(tasks) {
      try {
        localStorage.setItem('todo-tasks', JSON.stringify(tasks));
      } catch (e) {
        console.warn('Failed to save tasks to localStorage:', e);
      }
    }
  };

  // -------------------------------------------------------------
  // DOMRenderer
  // -------------------------------------------------------------
  const DOMRenderer = {
    taskListEl: null,

    init(taskListEl) {
      this.taskListEl = taskListEl;
    },

    render(tasks, onToggle, onDelete) {
      if (!this.taskListEl) return;
      this.taskListEl.innerHTML = '';
      for (const task of tasks) {
        const element = this.createTaskElement(task, onToggle, onDelete);
        this.taskListEl.appendChild(element);
      }
    },

    createTaskElement(task, onToggle, onDelete) {
      const li = document.createElement('li');
      li.className = 'task-item';
      if (task.completed) {
        li.classList.add('completed');
      }
      li.dataset.id = task.id;

      const checkbox = document.createElement('input');
      checkbox.type = 'checkbox';
      checkbox.className = 'task-checkbox';
      checkbox.checked = task.completed;
      checkbox.addEventListener('change', () => {
        onToggle(task.id);
      });

      const span = document.createElement('span');
      span.className = 'task-text';
      span.textContent = task.text;

      const deleteBtn = document.createElement('button');
      deleteBtn.className = 'delete-btn';
      deleteBtn.textContent = '✕';
      deleteBtn.setAttribute('aria-label', 'Delete task');
      deleteBtn.addEventListener('click', () => {
        onDelete(task.id);
      });

      li.appendChild(checkbox);
      li.appendChild(span);
      li.appendChild(deleteBtn);
      return li;
    }
  };

  // -------------------------------------------------------------
  // TaskManager
  // -------------------------------------------------------------
  const TaskManager = {
    state: [],

    init() {
      const taskListEl = document.getElementById('task-list');
      if (!taskListEl) {
        console.error('Task list element not found');
        return;
      }
      DOMRenderer.init(taskListEl);

      this.state = StorageManager.getTasks();
      this.render();

      // Bind event listeners
      const addBtn = document.getElementById('add-btn');
      const taskInput = document.getElementById('task-input');
      if (addBtn && taskInput) {
        addBtn.addEventListener('click', () => this.handleAdd(taskInput));
        taskInput.addEventListener('keydown', (e) => {
          if (e.key === 'Enter') {
            this.handleAdd(taskInput);
          }
        });
      }
    },

    handleAdd(inputEl) {
      const text = inputEl.value.trim();
      if (text === '') {
        inputEl.focus();
        return;
      }
      this.addTask(text);
      inputEl.value = '';
      inputEl.focus();
    },

    addTask(text) {
      const task = {
        id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
        text: text,
        completed: false
      };
      this.state.push(task);
      this._persistAndRender();
    },

    toggleTask(id) {
      const task = this.state.find(t => t.id === id);
      if (task) {
        task.completed = !task.completed;
        this._persistAndRender();
      }
    },

    deleteTask(id) {
      this.state = this.state.filter(t => t.id !== id);
      this._persistAndRender();
    },

    _persistAndRender() {
      StorageManager.saveTasks(this.state);
      this.render();
    },

    render() {
      DOMRenderer.render(
        this.state,
        (id) => this.toggleTask(id),
        (id) => this.deleteTask(id)
      );
    }
  };

  // -------------------------------------------------------------
  // Initialize
  // -------------------------------------------------------------
  document.addEventListener('DOMContentLoaded', () => {
    TaskManager.init();
  });

})();