"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
export function useConfirmation() {
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
        className="max-w-[calc(100%-2rem)] rounded-control bg-paper p-6 backdrop:bg-black/30"
        onCancel={(e) => {
          e.preventDefault();
          finish(false);
        }}
      >
        <p>{message}</p>
        <div className="mt-5 flex justify-end gap-3">
          <Button onClick={() => finish(true)}>确定</Button>
          <Button autoFocus onClick={() => finish(false)}>
            取消
          </Button>
        </div>
      </dialog>
    ),
  };
}
