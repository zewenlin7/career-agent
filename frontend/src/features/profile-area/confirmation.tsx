"use client";
import { useEffect, useRef, useState, useId } from "react";
import { Button } from "@/components/ui/button";
export function useConfirmation(accept = "确定", cancel = "取消", title?: string) {
  const id = useId();
  const [message, setMessage] = useState("");
  const dialog = useRef<HTMLDialogElement>(null);
  const resolve = useRef<(value: boolean) => void>(() => {});
  useEffect(() => {
    if (message) dialog.current?.showModal();
  }, [message]);
  function finish(value: boolean) {
    dialog.current?.close();
    setMessage("");
    resolve.current(value);
  }
  return {
    confirm: (text: string) =>
      new Promise<boolean>((done) => {
        resolve.current = done;
        setMessage(text);
      }),
    confirmation: (
      <dialog
        ref={dialog}
        aria-labelledby={title && message ? `${id}-title` : undefined}
        aria-describedby={`${id}-body`}
        className="fixed inset-0 m-auto w-[min(32rem,calc(100%-2rem))] rounded-control bg-paper p-6 backdrop:bg-black/30"
        onCancel={(e) => {
          e.preventDefault();
          finish(false);
        }}
      >
        {title && (
          <h2 id={`${id}-title`} className="mb-3 text-xl font-semibold">
            {title}
          </h2>
        )}
        <p id={`${id}-body`} className="text-base font-normal leading-relaxed">
          {message}
        </p>
        <div className="mt-5 flex justify-end gap-3">
          <Button onClick={() => finish(true)}>{accept}</Button>
          {cancel && (
            <Button autoFocus onClick={() => finish(false)}>
              {cancel}
            </Button>
          )}
        </div>
      </dialog>
    ),
  };
}
