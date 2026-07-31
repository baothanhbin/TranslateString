#!/usr/bin/env python3
"""Translate Android strings.xml resources into multiple locale folders."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


DEFAULT_LOCALES = {
    "hi": ("Hindi", "hi", "values-hi"),
    "es": ("Spanish", "es", "values-es"),
    "fr": ("French", "fr", "values-fr"),
    "en-GB": ("English (UK)", "en-GB", "values-en-rGB"),
    "en-US": ("English (US)", "en-US", "values-en-rUS"),
    "de": ("German", "de", "values-de"),
    "id": ("Indonesian", "id", "values-in"),
    "pt": ("Portuguese", "pt", "values-pt"),
    "zh": ("Chinese", "zh-CN", "values-zh"),
}

STRING_RE = re.compile(
    r"<string\b(?P<attrs>[^>]*)\bname\s*=\s*(['\"])(?P<name>[^'\"]+)\2(?P<attrs2>[^>]*)>"
    r"(?P<value>.*?)</string>",
    re.DOTALL,
)
ATTR_RE = re.compile(r"([:\w-]+)\s*=\s*(['\"])(.*?)\2", re.DOTALL)
COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
TOKEN_RE = re.compile(
    r"(<[^>]+>|%\d+\$[a-zA-Z]|%[a-zA-Z]|%%|\\n|\\t|\\r|\\'|\\\"|https?://\S+)"
)


@dataclass(frozen=True)
class AndroidString:
    name: str
    attrs: dict[str, str]
    value: str


def parse_strings(xml_text: str) -> list[AndroidString]:
    """Parse <string> entries while keeping inline markup as text."""
    xml_text = COMMENT_RE.sub("", xml_text)
    strings: list[AndroidString] = []

    for match in STRING_RE.finditer(xml_text):
        attrs_text = f"{match.group('attrs')} {match.group('attrs2')}"
        attrs = {key: value for key, _, value in ATTR_RE.findall(attrs_text)}
        name = match.group("name")
        attrs["name"] = name
        strings.append(AndroidString(name=name, attrs=attrs, value=match.group("value")))

    return strings


def should_translate(item: AndroidString) -> bool:
    if item.attrs.get("translatable", "").lower() == "false":
        return False
    visible_text = re.sub(r"<[^>]+>", "", item.value)
    visible_text = TOKEN_RE.sub("", visible_text)
    return any(ch.isalpha() for ch in html.unescape(visible_text))


def protect_tokens(text: str) -> tuple[str, dict[str, str]]:
    tokens: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        key = f"__TT{len(tokens)}__"
        tokens[key] = match.group(0)
        return key

    return TOKEN_RE.sub(replace, html.unescape(text)), tokens


def restore_tokens(text: str, tokens: dict[str, str]) -> str:
    for key, value in tokens.items():
        text = text.replace(key, value)
        text = text.replace(key.lower(), value)
        text = text.replace(key.replace("_", " "), value)
    return text


def translate_google(text: str, target: str, source: str = "auto") -> str:
    query = urllib.parse.urlencode(
        {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }
    )
    url = f"https://translate.googleapis.com/translate_a/single?{query}"
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})

    with urllib.request.urlopen(request, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    return "".join(part[0] for part in payload[0] if part and part[0])


def escape_preserving_tags(text: str) -> str:
    parts = re.split(r"(<[^>]+>)", text)
    escaped: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("<") and part.endswith(">"):
            escaped.append(part)
        else:
            escaped.append(html.escape(part, quote=False))
    return "".join(escaped)


def attrs_to_xml(attrs: dict[str, str]) -> str:
    parts = []
    for key, value in attrs.items():
        if key == "name":
            continue
        parts.append(f'{key}="{html.escape(value, quote=True)}"')
    return (" " + " ".join(parts)) if parts else ""


def load_cache(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_cache(path: Path, cache: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(cache, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def translate_value(
    value: str,
    target: str,
    source: str,
    cache: dict[str, str],
    sleep_seconds: float,
) -> str:
    protected, tokens = protect_tokens(value)
    cache_key = json.dumps([source, target, protected], ensure_ascii=False)

    if cache_key not in cache:
        cache[cache_key] = translate_google(protected, target=target, source=source)
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)

    return restore_tokens(cache[cache_key], tokens)


def write_locale_file(
    output_root: Path,
    folder: str,
    items: Iterable[tuple[AndroidString, str]],
) -> Path:
    locale_dir = output_root / folder
    locale_dir.mkdir(parents=True, exist_ok=True)
    target_file = locale_dir / "strings.xml"

    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<resources>"]
    for item, translated in items:
        attr_xml = attrs_to_xml(item.attrs)
        value_xml = escape_preserving_tags(translated)
        lines.append(f'    <string name="{html.escape(item.name, quote=True)}"{attr_xml}>{value_xml}</string>')
    lines.append("</resources>")
    lines.append("")

    target_file.write_text("\n".join(lines), encoding="utf-8")
    return target_file


def parse_locale_list(raw: str) -> list[str]:
    locales = [part.strip() for part in raw.split(",") if part.strip()]
    unknown = [locale for locale in locales if locale not in DEFAULT_LOCALES]
    if unknown:
        supported = ", ".join(DEFAULT_LOCALES)
        raise SystemExit(f"Unsupported locale(s): {', '.join(unknown)}. Supported: {supported}")
    return locales


def translate_file(
    input_path: Path,
    output_path: Path,
    locales: list[str],
    source_lang: str = "auto",
    cache_path: Path = Path(".translate-cache.json"),
    sleep_seconds: float = 0.05,
    progress: Callable[[str], None] | None = None,
) -> list[Path]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    source_xml = input_path.read_text(encoding="utf-8-sig")
    strings = parse_strings(source_xml)
    translatable = [item for item in strings if should_translate(item)]
    if not translatable:
        raise ValueError("No translatable <string> entries found.")

    cache = load_cache(cache_path)
    output_path.mkdir(parents=True, exist_ok=True)
    saved_files: list[Path] = []

    if progress:
        progress(f"Found {len(strings)} strings, translating {len(translatable)} entries.")

    for locale in locales:
        label, google_code, folder = DEFAULT_LOCALES[locale]
        translated_items: list[tuple[AndroidString, str]] = []

        if progress:
            progress(f"Translating {label} -> {folder}/strings.xml")

        for index, item in enumerate(translatable, start=1):
            translated = translate_value(
                item.value,
                target=google_code,
                source=source_lang,
                cache=cache,
                sleep_seconds=sleep_seconds,
            )
            translated_items.append((item, translated))

            if progress and (index == 1 or index == len(translatable) or index % 10 == 0):
                progress(f"{label}: {index}/{len(translatable)}")

        target_file = write_locale_file(output_path, folder, translated_items)
        save_cache(cache_path, cache)
        saved_files.append(target_file)

        if progress:
            progress(f"Saved {target_file}")

    if progress:
        progress("Done.")

    return saved_files


def run_gui() -> int:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("Android String Translator")
    root.geometry("760x560")
    root.minsize(680, 500)

    input_var = tk.StringVar()
    output_var = tk.StringVar(value=str(Path.cwd() / "res"))
    source_var = tk.StringVar(value="auto")
    cache_var = tk.StringVar(value=str(Path.cwd() / ".translate-cache.json"))
    locale_vars = {key: tk.BooleanVar(value=True) for key in DEFAULT_LOCALES}
    running = tk.BooleanVar(value=False)

    main = ttk.Frame(root, padding=16)
    main.pack(fill="both", expand=True)
    main.columnconfigure(1, weight=1)
    main.rowconfigure(7, weight=1)

    def choose_input() -> None:
        path = filedialog.askopenfilename(
            title="Choose strings.xml",
            filetypes=[("Android strings", "strings.xml"), ("XML or text", "*.xml *.txt"), ("All files", "*.*")],
        )
        if path:
            input_var.set(path)
            if output_var.get() == str(Path.cwd() / "res"):
                output_var.set(str(Path(path).parent.parent if Path(path).parent.name.startswith("values") else Path(path).parent / "res"))

    def choose_output() -> None:
        path = filedialog.askdirectory(title="Choose output folder")
        if path:
            output_var.set(path)

    ttk.Label(main, text="Source strings.xml").grid(row=0, column=0, sticky="w", pady=(0, 8))
    ttk.Entry(main, textvariable=input_var).grid(row=0, column=1, sticky="ew", padx=8, pady=(0, 8))
    ttk.Button(main, text="Choose File", command=choose_input).grid(row=0, column=2, pady=(0, 8))

    ttk.Label(main, text="Output folder").grid(row=1, column=0, sticky="w", pady=(0, 8))
    ttk.Entry(main, textvariable=output_var).grid(row=1, column=1, sticky="ew", padx=8, pady=(0, 8))
    ttk.Button(main, text="Choose Folder", command=choose_output).grid(row=1, column=2, pady=(0, 8))

    ttk.Label(main, text="Source language").grid(row=2, column=0, sticky="w", pady=(0, 8))
    ttk.Entry(main, textvariable=source_var, width=12).grid(row=2, column=1, sticky="w", padx=8, pady=(0, 8))
    ttk.Label(main, text="Use auto, en, vi...").grid(row=2, column=1, sticky="w", padx=(100, 8), pady=(0, 8))

    locales_frame = ttk.LabelFrame(main, text="Languages", padding=12)
    locales_frame.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(4, 12))
    for index, (key, (label, _, folder)) in enumerate(DEFAULT_LOCALES.items()):
        text = f"{label} ({folder})"
        ttk.Checkbutton(locales_frame, text=text, variable=locale_vars[key]).grid(
            row=index // 3,
            column=index % 3,
            sticky="w",
            padx=(0, 24),
            pady=4,
        )

    controls = ttk.Frame(main)
    controls.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(0, 12))
    controls.columnconfigure(0, weight=1)

    ttk.Label(main, text="Progress").grid(row=5, column=0, sticky="w")
    progress_bar = ttk.Progressbar(main, mode="indeterminate")
    progress_bar.grid(row=6, column=0, columnspan=3, sticky="ew", pady=(0, 8))

    log_box = tk.Text(main, height=12, wrap="word")
    log_box.grid(row=7, column=0, columnspan=3, sticky="nsew")
    log_box.configure(state="disabled")

    def append_log(message: str) -> None:
        log_box.configure(state="normal")
        log_box.insert("end", message + "\n")
        log_box.see("end")
        log_box.configure(state="disabled")

    def set_running(value: bool) -> None:
        running.set(value)
        start_button.configure(state="disabled" if value else "normal")
        if value:
            progress_bar.start(10)
        else:
            progress_bar.stop()

    def start_translation() -> None:
        input_path = Path(input_var.get().strip())
        output_path = Path(output_var.get().strip())
        selected = [key for key, var in locale_vars.items() if var.get()]

        if not input_path:
            messagebox.showwarning("Missing file", "Please choose a strings.xml file.")
            return
        if not selected:
            messagebox.showwarning("Missing languages", "Please choose at least one language.")
            return
        if running.get():
            return

        set_running(True)
        append_log("Starting...")

        def worker() -> None:
            try:
                saved = translate_file(
                    input_path=input_path,
                    output_path=output_path,
                    locales=selected,
                    source_lang=source_var.get().strip() or "auto",
                    cache_path=Path(cache_var.get().strip() or ".translate-cache.json"),
                    sleep_seconds=0.05,
                    progress=lambda message: root.after(0, append_log, message),
                )
            except Exception as exc:
                root.after(0, append_log, f"Error: {exc}")
                root.after(0, messagebox.showerror, "Translate failed", str(exc))
            else:
                root.after(0, append_log, f"Created {len(saved)} files in {output_path}")
                root.after(0, messagebox.showinfo, "Done", f"Created {len(saved)} files.")
            finally:
                root.after(0, set_running, False)

        threading.Thread(target=worker, daemon=True).start()

    start_button = ttk.Button(controls, text="Translate", command=start_translation)
    start_button.grid(row=0, column=1, sticky="e")

    root.mainloop()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Translate Android strings.xml into values-* locale folders."
    )
    parser.add_argument("input", type=Path, nargs="?", help="Path to the source strings.xml file")
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("translated"),
        help="Output root directory. Default: translated",
    )
    parser.add_argument(
        "--source-lang",
        default="auto",
        help="Source language code for Google Translate. Default: auto",
    )
    parser.add_argument(
        "--locales",
        default=",".join(DEFAULT_LOCALES.keys()),
        help="Comma-separated locale list. Default: hi,es,fr,en-GB,en-US,de,id,pt,zh",
    )
    parser.add_argument(
        "--cache",
        type=Path,
        default=Path(".translate-cache.json"),
        help="Translation cache file. Default: .translate-cache.json",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=0.05,
        help="Delay between uncached requests in seconds. Default: 0.05",
    )
    args = parser.parse_args()

    if args.input is None:
        return run_gui()

    locales = parse_locale_list(args.locales)
    translate_file(
        input_path=args.input,
        output_path=args.output,
        locales=locales,
        source_lang=args.source_lang,
        cache_path=args.cache,
        sleep_seconds=args.sleep,
        progress=print,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
