# UI Improvement Plan - Sharrowkin Frontend

**Date**: 2026-05-23 18:17 UTC  
**Goal**: Улучшить UI для лучшего UX

---

## 🎨 Текущее состояние UI

### ✅ Что уже есть (хорошо):
- **Next.js 14** - современный фреймворк
- **Radix UI** - качественные компоненты
- **Framer Motion** - анимации
- **Tailwind CSS** - стилизация
- **Real-time WebSocket** - live updates
- **Компоненты**:
  - Agent status badge
  - Phase timeline
  - Energy visualization
  - Thinking indicator
  - Tools panel
  - Diff viewer
  - Terminal emulator

### 📊 Структура:
```
ui/
├── app/
│   ├── chat/ - главный чат
│   ├── dashboard/ - дашборд
│   ├── personas/ - персоны
│   ├── autonomous/ - автономный режим
│   └── review/ - код ревью
├── components/
│   ├── chat/ - 30+ компонентов чата
│   └── ui/ - базовые UI компоненты
```

---

## 🚀 Улучшения (приоритеты)

### Priority 1: Визуальные улучшения (30 мин)

#### 1.1 Современный градиент фон
```tsx
// app/globals.css
body {
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  background-attachment: fixed;
}
```

#### 1.2 Glassmorphism эффекты
```tsx
// Для карточек и панелей
className="backdrop-blur-xl bg-white/10 border border-white/20 shadow-2xl"
```

#### 1.3 Плавные анимации
```tsx
// Framer Motion transitions
<motion.div
  initial={{ opacity: 0, y: 20 }}
  animate={{ opacity: 1, y: 0 }}
  transition={{ duration: 0.3 }}
>
```

### Priority 2: UX улучшения (45 мин)

#### 2.1 Лучшая индикация статуса агента
- Пульсирующий индикатор при работе
- Прогресс бар для каждой фазы
- Анимированные иконки инструментов

#### 2.2 Улучшенный diff viewer
- Syntax highlighting
- Fold/unfold блоки
- Side-by-side view

#### 2.3 Быстрые действия
- Keyboard shortcuts (Cmd+K)
- Quick actions menu
- Drag & drop файлов

### Priority 3: Новые фичи (60 мин)

#### 3.1 Dark mode
```tsx
// Переключатель темы
<ThemeToggle />
```

#### 3.2 Notifications
```tsx
// Toast уведомления
import { toast } from "sonner"
toast.success("Task completed!")
```

#### 3.3 Command palette
```tsx
// Cmd+K меню
<CommandPalette />
```

---

## 🎯 Конкретные улучшения

### 1. Главная страница чата

**Файл**: `ui/app/chat/page.tsx`

**Улучшения**:
- Hero section с анимацией
- Quick start cards
- Recent conversations

### 2. Chat Shell

**Файл**: `ui/components/chat/chat-shell.tsx`

**Улучшения**:
- Лучший layout (3-колонки)
- Collapsible sidebars
- Floating action button

### 3. Message List

**Улучшения**:
- Markdown рендеринг
- Code syntax highlighting
- Copy button для кода
- Reactions (👍 👎)

### 4. Agent Status

**Улучшения**:
- Real-time phase progress
- Energy visualization
- Memory usage graph
- Tool activity timeline

---

## 📝 Конкретный план действий

### Шаг 1: Обновить globals.css (5 мин)
- Добавить градиент фон
- Улучшить типографику
- Добавить CSS переменные для темы

### Шаг 2: Улучшить chat-shell.tsx (15 мин)
- Добавить glassmorphism
- Улучшить layout
- Добавить анимации

### Шаг 3: Улучшить message-list (15 мин)
- Syntax highlighting для кода
- Copy buttons
- Better spacing

### Шаг 4: Улучшить agent status (15 мин)
- Animated progress bars
- Phase timeline с иконками
- Energy visualization

### Шаг 5: Добавить dark mode (20 мин)
- Theme provider
- Toggle button
- CSS variables

### Шаг 6: Добавить notifications (10 мин)
- Sonner toast
- Success/error messages
- Progress notifications

---

## 🎨 Дизайн система

### Цвета:
```css
:root {
  --primary: #667eea;
  --secondary: #764ba2;
  --success: #10b981;
  --error: #ef4444;
  --warning: #f59e0b;
  --background: #fafafa;
  --foreground: #1a1a1a;
}
```

### Spacing:
- xs: 4px
- sm: 8px
- md: 16px
- lg: 24px
- xl: 32px

### Border radius:
- sm: 8px
- md: 12px
- lg: 16px
- xl: 24px

---

## ✅ Критерии успеха

- [ ] Современный визуальный дизайн
- [ ] Плавные анимации (60fps)
- [ ] Dark mode работает
- [ ] Notifications показываются
- [ ] Keyboard shortcuts работают
- [ ] Mobile responsive
- [ ] Accessibility (a11y) соблюдается

---

**Время**: ~2 часа  
**Сложность**: Средняя  
**Приоритет**: Высокий
