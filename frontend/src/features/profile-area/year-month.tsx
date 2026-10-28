"use client";
import { useId, useState } from "react";
import { control } from "../workspace/ui";

/** Text entry avoids browser-locale dependent month names. */
export function YearMonth({
  value,
  onChange,
  id,
}: {
  id?: string;
  value: string;
  onChange: (value: string) => void;
}) {
  const suggestions = useId();
  const [touched, setTouched] = useState(false);
  const invalid = !!value && !/^\d{4}-(0[1-9]|1[0-2])$/.test(value);
  const year = /^\d{4}/.exec(value)?.[0];
  return (
    <>
      <input
        id={id}
        aria-invalid={touched && invalid}
        aria-describedby={touched && invalid ? `${suggestions}-error` : undefined}
        onBlur={() => setTouched(true)}
        className={control}
        type="text"
        inputMode="numeric"
        placeholder="YYYY-MM"
        pattern="[0-9]{4}-(0[1-9]|1[0-2])"
        maxLength={7}
        value={value}
        list={year ? suggestions : undefined}
        onChange={(event) => onChange(event.target.value)}
      />
      {touched && invalid && (
        <p id={`${suggestions}-error`} role="alert" className="text-sm text-error">
          请使用 YYYY-MM 格式填写年月。
        </p>
      )}
      {year && (
        <datalist id={suggestions}>
          {Array.from({ length: 12 }, (_, index) => (
            <option key={index} value={`${year}-${String(index + 1).padStart(2, "0")}`}>
              {index + 1}月
            </option>
          ))}
        </datalist>
      )}
    </>
  );
}
