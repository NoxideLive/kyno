# Groq JSON Mode and Widget Architecture for Kyno

This document outlines the research and design for implementing a structured widget system in Kyno chat using Groq's JSON mode and Structured Outputs.

## 1. Groq JSON Mode & Structured Outputs

Groq provides two primary ways to get structured data from models: **JSON Object Mode** and **Structured Outputs (JSON Schema)**.

### Structured Outputs (Recommended)
Structured Outputs ensure that the model's response strictly adheres to a provided JSON Schema.

- **API Parameter**: `response_format: { type: "json_schema", json_schema: { name: "...", strict: true, schema: { ... } } }`
- **Strict Mode (`strict: true`)**:
    - **Guarantee**: 100% schema compliance via constrained decoding.
    - **Requirements**: 
        - All object properties must be listed in the `required` array.
        - All objects must set `additionalProperties: false`.
    - **Model Compatibility**: Currently supported by `openai/gpt-oss-20b` and `openai/gpt-oss-120b`.
- **Best-effort Mode (`strict: false`)**:
    - **Guarantee**: Best-effort compliance.
    - **Requirements**: More flexible (optional fields allowed).
    - **Model Compatibility**: Supported by most Llama and Mixtral models on Groq.

### JSON Object Mode
- **API Parameter**: `response_format: { type: "json_object" }`
- **Guarantee**: Valid JSON syntax, but no schema enforcement.
- **Requirements**: You **must** include instructions in the system prompt (e.g., "Respond in JSON") to avoid errors.

### Error Handling & Retries
- **Strict Mode**: Groq may still reject generation server-side if output violates schema (`failed_generation` in error body). Kyno logs the full error and retries with **JSON Object Mode** (`response_format: { type: "json_object" }`).
- **Best-effort/JSON Mode**: Use a validation library (like **Zod**) to parse the output. If parsing fails, Kyno fills structurally missing empty fields, then **retries** with a correction message (no type downgrading).
- **Retries**: Up to 3 attempts — strict `json_schema` first, then `json_object`. On failure, the server appends synthetic assistant/user turns to the **Groq-only** thread with a correction hint and the rejected JSON. These turns are **not** saved to Convex or shown in the UI.

---

## 2. Widget System Design for Kyno

The goal is to allow the LLM to choose between a standard text response and an interactive widget.

### Widget Types
1. **`response`**: A standard assistant message.
2. **`question`**: Multiple-choice (2–4 options).
3. **`confirm`**: Yes/no decision.
4. **`math`**: Display-only LaTeX (no prose). Use a separate `response` widget for explanation.

### Batch response shape
Groq returns one JSON object per turn:

```json
{
  "widgets": [
    { "type": "response", "content": "…", "question": "", "suggestedAnswers": [] },
    { "type": "math", "content": "x = \\frac{-b}{2a}", "question": "", "suggestedAnswers": [] }
  ]
}
```

Each widget is stored as its own assistant message row in Convex.

### Flat Object Schema (Groq Strict Mode Requirement)
Groq strict JSON schema (`strict: true`) requires the **top level** to be `type: "object"` and **forbids** `anyOf`/`oneOf`/`enum`/`not` at the top level.

Use a batch wrapper; each item is a flat widget object:

```json
{
  "type": "object",
  "properties": {
    "widgets": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "type": { "type": "string", "enum": ["response", "question", "confirm", "math"] },
          "content": { "type": "string" },
          "question": { "type": "string" },
          "suggestedAnswers": { "type": "array", "items": { "type": "string" } }
        },
        "required": ["type", "content", "question", "suggestedAnswers"],
        "additionalProperties": false
      },
      "minItems": 1
    }
  },
  "required": ["widgets"],
  "additionalProperties": false
}
```

Normalization (Zod) converts flat output to the internal discriminated union after parsing.

**Invalid (causes Groq error):**
```json
{ "anyOf": [ { ...response... }, { ...question... } ] }
```

### LLM Selection Logic
The system prompt will instruct the LLM:
> "You are a helpful assistant. You can respond with a plain message or an interactive question. If the user needs to make a choice, use the 'question' widget. Otherwise, use 'response'."

### Frontend Rendering
- **`ChatMessageContent.vue`**: Detects if the content is valid JSON. If so, it switches to `format="widget"`.
- **Components**:
    - `WidgetResponse.vue`: Renders the `content` as markdown.
    - `WidgetQuestion.vue`: Renders multiple-choice with pill buttons.
    - `WidgetMath.vue`: Renders LaTeX via KaTeX (display mode).

---

## 3. LangChain Evaluation

### Should Kyno use LangChain.js?
**Recommendation: No (for now).**

- **Pros**: `withStructuredOutput` simplifies schema conversion and retries.
- **Cons**: LangChain adds significant bundle size and abstraction overhead. Convex Actions already provide a clean environment for `fetch()` calls to Groq.
- **Alternative**: Use **Zod** directly in the Convex Action. It provides type safety and validation with much less weight.

---

## 4. Implementation Plan (Checklist)

### Backend (Convex)
- [ ] **Update `convex/chat.ts`**:
    - Add `mode: 'json'` support to `sendMessage`.
    - Implement `response_format` in the Groq fetch call.
    - Add Zod validation for the assistant's response.
- [ ] **Update `convex/conversations.ts`**: Ensure `persistExchange` can handle JSON strings in `assistantContent`.

### Frontend (Vue)
- [ ] **New Components**:
    - `src/components/widgets/WidgetResponse.vue`
    - `src/components/widgets/WidgetQuestion.vue`
- [ ] **Update `ChatMessageContent.vue`**:
    - Add logic to parse `content` as JSON if `format="widget"`.
    - Dynamically render the correct widget component.
- [ ] **Update `useGroqChat.ts`**:
    - Pass `mode: 'json'` to the `sendMessage` action.
    - Handle potential parsing errors gracefully.

### Prompt Engineering
- [ ] **Update System Prompt**: Add instructions for widget selection and the JSON schema.

### Backward Compatibility
- [ ] **Migration**: Existing text-only messages in Convex will have `format="text"`. `ChatMessageContent.vue` should default to text rendering if JSON parsing fails.

---

## 5. Debugging Groq & Widget Issues

### Convex logs (recommended)

Kyno emits structured `[kyno:groq]` logs via `console.log` in Convex actions. View them in:

- **Convex Dashboard** → your deployment → **Logs** (filter by `[kyno:groq]`)
- **`npx convex dev`** terminal while developing locally

Logs never include `GROQ_API_KEY` or JWT tokens.

| Event | When | Key fields |
|-------|------|------------|
| `request` | Before each Groq `fetch` | `model`, `mode`, `messageCount`, `schemaName`, `systemPrompt.length`, `systemPrompt.hash` |
| `response_success` | Groq returned content | `latencyMs`, `usage`, `contentLength` |
| `response_failure` | Groq HTTP error or empty body | `status`, `groqMessage`, `failedGeneration` (truncated) |
| `validation_failure` | Zod rejected assistant JSON | `rawContent` (truncated), `zodIssues` |
| `validation_success` | Parsed widget OK | `widgetCount`, `widgetTypes` |
| `retry` | Next attempt starting | `attempt`, `reason`, `correctionPreview` (truncated hint sent to model) |
| `send_message` | `sendMessage` action entry | `model`, `mode`, `hasConversationId` |

### Success flow (example)

```
[kyno:groq] send_message {"model":"openai/gpt-oss-20b","mode":"json","messageCount":3,"hasConversationId":true}
[kyno:groq] request {"model":"openai/gpt-oss-20b","mode":"json","messageCount":4,"schemaName":"kyno_widget","systemPrompt":{"length":412,"hash":"a1b2c3d4"}}
[kyno:groq] response_success {"mode":"json","latencyMs":842,"usage":{"prompt_tokens":120,"completion_tokens":45,"total_tokens":165},"contentLength":87}
[kyno:groq] validation_success {"widgetType":"response","usedDefaults":false}
```

### Failure flow (Groq schema mismatch → retry)

When Groq rejects strict schema output (e.g. missing `question` / `suggestedAnswers` on a `response` widget):

```
[kyno:groq] response_failure {"status":400,"code":"GROQ_SCHEMA_MISMATCH","groqMessage":"Generated JSON does not match the expected schema...","failedGeneration":"{\"type\":\"response\",\"content\":\"Hello\"}…"}
[kyno:groq] retry {"attempt":2,"reason":"groq_schema_mismatch","groqMessage":"...","failedGeneration":"..."}
[kyno:groq] request {"model":"...","mode":"json_object",...}
```

If both attempts fail, the client receives `GROQ_SCHEMA_MISMATCH` or `GROQ_INVALID_WIDGET` with a `details` field (`failedGeneration` or `rawSnippet`, truncated). In **dev**, the Vue chat UI appends these snippets to the error message.

### Client error codes

| Code | Meaning |
|------|---------|
| `GROQ_SCHEMA_MISMATCH` | Groq strict schema rejected generation; check `details.failedGeneration` |
| `GROQ_INVALID_WIDGET` | Got JSON back but validation failed after all retry attempts |
| `GROQ_REQUEST_FAILED` | Other Groq API error |
| `GROQ_EMPTY_RESPONSE` | 200 response with no assistant content |
