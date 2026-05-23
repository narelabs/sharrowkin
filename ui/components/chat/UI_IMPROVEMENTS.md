# UI Improvements - Workspace Panel & Streaming Edits

## Новые компоненты

### 1. WorkspacePanel (`workspace-panel.tsx`)
Боковая панель с деревом файлов проекта (как VS Code).

**Возможности**:
- Иерархическое дерево файлов и папок
- Иконки по типу файла (TypeScript, Python, JSON, и т.д.)
- Подсветка изменённых файлов
- Показ diff stats (+additions, -deletions)
- Автоматическое раскрытие папок с изменениями
- Клик по файлу открывает diff справа

**Использование**:
```tsx
<WorkspacePanel
  files={workspaceFiles}
  onFileClick={(path) => setActiveDiffFile(path)}
  selectedFile={selectedFile}
  className="w-64"
/>
```

### 2. StreamingEditedSteps (`streaming-edited-steps.tsx`)
Постепенное отображение изменённых файлов (не списком, а по одному).

**Возможности**:
- Файлы появляются один за другим с анимацией
- Показ статуса: pending → editing → done
- Diff stats для каждого файла
- Промежуточные сообщения агента между файлами
- Клик по файлу открывает diff

**Использование**:
```tsx
const streamingEdits = useStreamingEdits(message.toolSteps)

<StreamingEditedSteps
  edits={streamingEdits}
  onFileClick={onOpenDiff}
/>
```

### 3. FileDiffViewer (`file-diff-viewer.tsx`)
Улучшенный просмотр diff с подсветкой изменений.

**Возможности**:
- Построчный diff с номерами строк
- Зелёная подсветка добавленных строк (bg-emerald-50)
- Красная подсветка удалённых строк (bg-red-50)
- Маркеры +/− для каждой строки
- Кнопка Copy для копирования кода
- Поддержка новых файлов (все строки зелёные)

**Использование**:
```tsx
<FileDiffViewer
  filename="models/cart.py"
  oldContent={oldCode}
  newContent={newCode}
/>
```

## Интеграция в message-bubble.tsx

Добавлено:
1. Импорт `StreamingEditedSteps` и `useStreamingEdits`
2. Hook для преобразования tool steps в streaming edits
3. Отображение streaming edits в timeline

```tsx
// В MessageBubble
const streamingEdits = useStreamingEdits(message.toolSteps)

// В expandedSteps
{streamingEdits.length > 0 && (
  <div className="py-2">
    <StreamingEditedSteps
      edits={streamingEdits}
      onFileClick={onOpenDiff}
    />
  </div>
)}
```

## Интеграция в chat-shell.tsx

Добавлено:
1. Состояние для workspace panel
2. Состояние для workspace files
3. Рендеринг WorkspacePanel слева от чата

```tsx
const [workspacePanelOpen, setWorkspacePanelOpen] = useState(false)
const [workspaceFiles, setWorkspaceFiles] = useState([])
const [selectedFile, setSelectedFile] = useState<string>()

{workspacePanelOpen && (
  <WorkspacePanel
    files={workspaceFiles}
    onFileClick={(path) => {
      setSelectedFile(path)
      setActiveDiffFile(path)
    }}
    selectedFile={selectedFile}
    className="w-64 shrink-0"
  />
)}
```

## Как это работает

### Workflow для пользователя:

1. **Агент начинает работу** → "Working for 3s"
2. **Файлы появляются постепенно**:
   - `models/cart.py +30` (editing...)
   - → "Отлично, я добавил корзину"
   - `api/routes.py +15 -3` (editing...)
   - → "Теперь создаю API endpoints"
   - `tests/test_cart.py +45` (done)
3. **Клик по файлу** → открывается diff справа с зелёной подсветкой
4. **Workspace panel** → показывает все изменённые файлы в дереве

### Преимущества:

- ✅ Постепенное отображение (не всё сразу)
- ✅ Промежуточные сообщения агента
- ✅ Визуальная подсветка изменений
- ✅ Удобная навигация по файлам
- ✅ Как в VS Code

## TODO

- [ ] Подключить реальные данные workspace files из backend
- [ ] Добавить кнопку toggle для workspace panel
- [ ] Синхронизировать workspace files с tool steps
- [ ] Добавить syntax highlighting в FileDiffViewer
- [ ] Добавить поддержку binary files (images)
