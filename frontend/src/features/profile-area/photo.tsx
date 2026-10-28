"use client";
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { ApiError, endpoint, useAction } from "../workspace/client";
import { Field } from "../workspace/ui";
import { InlineError } from "./common";
export function PhotoPreview({ id }: { id: string }) {
  return (
    <div className="mt-4">
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src={endpoint(`profile-photos/${id}`)}
        alt="个人照片"
        className="h-32 w-24 rounded-control object-contain"
      />
    </div>
  );
}
export function Photo({
  id,
  onChange,
  onBusy,
}: {
  id: string | null;
  onChange: (id: string | null) => void;
  onBusy?: (busy: boolean) => void;
}) {
  const action = useAction();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  function upload(file?: File) {
    if (!file || action.busy) return;
    void action.run(async () => {
      if (file.size > 5_000_000) throw new ApiError("photo_too_large");
      if (!["image/jpeg", "image/png", "image/webp"].includes(file.type))
        throw new ApiError("invalid_photo");
      const response = await fetch(endpoint("profile-photos"), {
        method: "POST",
        headers: { "Content-Type": file.type },
        body: file,
      });
      const result = await response.json();
      if (!response.ok) throw new ApiError(result.error?.code || "invalid_photo");
      onChange(result.id);
    });
  }
  useEffect(() => {
    onBusy?.(action.busy);
    return () => onBusy?.(false);
  }, [action.busy, onBusy]);
  return (
    <div
      aria-label="照片上传区域"
      className={`space-y-3 rounded-control border p-3 ${dragging ? "border-accent bg-paper" : "border-transparent"}`}
      onDragOver={(e) => {
        e.preventDefault();
        setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        upload(e.dataTransfer.files[0]);
      }}
    >
      <Field label="个人照片（选填）">
        <input
          ref={input}
          className="sr-only"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          disabled={action.busy}
          onChange={(e) => upload(e.target.files?.[0])}
        />
      </Field>
      <Button disabled={action.busy} onClick={() => input.current?.click()}>
        {action.busy ? "正在上传…" : id ? "更换" : "选择照片"}
      </Button>
      <p className="text-sm text-secondary">JPG、PNG 或 WebP，最大 5 MB</p>
      {id && (
        <>
          <PhotoPreview id={id} />
          <Button onClick={() => onChange(null)}>移除</Button>
        </>
      )}
      <InlineError code={action.error} />
    </div>
  );
}
