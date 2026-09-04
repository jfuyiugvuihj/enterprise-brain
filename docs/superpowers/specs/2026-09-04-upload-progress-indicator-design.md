# Upload Progress Indicator Design

## Scope

Improve the knowledge-base upload queue in `frontend/src/components/DocPanel.vue`.
The backend upload API and its response format remain unchanged.

## UI Behavior

- While an item has `status: "uploading"`, show a compact SVG progress ring with
  a CSS rotation animation.
- The status message changes from `上传中...` to `解析入库中...` after the
  multipart upload is accepted and the request is waiting for the final result.
- Completed, skipped, and failed uploads retain their existing terminal-state
  icons and messages.
- The queue item uses an accessible status label so the state is still clear
  without relying on the animation.

## Data Flow

`uploadFiles` owns each upload item. It initializes the item as uploading,
updates its message after the request begins, and changes `status` only when
the API returns or raises an error. The template derives the icon from the
existing `item.status`; no new shared state or backend polling is introduced.

## Verification

- Add a source-level frontend regression test that requires the progress-ring
  markup, the loading status label, and the rotating CSS animation.
- Run the focused frontend test, the full Python suite, and `npm run build`.
