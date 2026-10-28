"use client";
import { useRef, useState } from "react";
import { control } from "../workspace/ui";
import { InlineError } from "./common";
import { useAction } from "../workspace/client";

/** Renaming is independent from content editing; only Enter commits. */
export function InlineName({
  value,
  label,
  save,
  disabled = false,
}: {
  value: string;
  label: string;
  save: (name: string) => Promise<void>;
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);
  const submitting = useRef(false);
  const action = useAction();
  function begin() {
    if (disabled || action.busy) return;
    setText(value);
    setEditing(true);
  }
  return (
    <div className="min-w-0">
      {editing ? (
        <input
          autoFocus
          aria-label={label}
          className={control}
          value={text}
          disabled={action.busy}
          onChange={(event) => setText(event.target.value)}
          onBlur={() => {
            if (!submitting.current) setEditing(false);
          }}
          onKeyDown={(event) => {
            if (event.nativeEvent.isComposing) return;
            if (event.key === "Escape") {
              event.preventDefault();
              setEditing(false);
            }
            if (event.key !== "Enter") return;
            event.preventDefault();
            if (!text.trim() || submitting.current) return;
            if (text.trim() === value) {
              setEditing(false);
              return;
            }
            submitting.current = true;
            void action
              .run(async () => {
                await save(text.trim());
                setEditing(false);
              })
              .finally(() => {
                submitting.current = false;
              });
          }}
        />
      ) : (
        <div className="flex items-center gap-2">
          <h2 className="break-words font-serif text-2xl" onDoubleClick={begin}>
            {value}
          </h2>
          <button
            type="button"
            className="shrink-0 p-2 text-sm text-secondary"
            aria-label={label}
            disabled={disabled}
            onClick={begin}
          >
            ✎
          </button>
        </div>
      )}
      <InlineError code={action.error} />
    </div>
  );
}
